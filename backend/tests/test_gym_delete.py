import pytest
from fastapi.testclient import TestClient

from coach import api, db, gym
from coach.secrets import write_secret


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    value = {
        "id": "draft",
        "title": "Synthetic workout",
        "started_at": "2026-01-01T12:00:00Z",
        "finished_at": None,
        "revision": 2,
        "exercises": [
            {
                "id": "one",
                "exercise_id": "synthetic",
                "logged_sets": [{"weight": 10, "reps": 8, "seconds": None, "done": True}],
            }
        ],
    }
    db.upsert_record("gym_workout", "draft", value)
    db.upsert_record("gym_program", "program", {"id": "program"})
    db.upsert_record("gym_excel_history", "source", {"id": "source"})
    return tmp_path, value


def test_delete_incomplete_workout_preserves_program_and_import_history(workspace):
    assert gym.delete_workout("draft", 2) == {"deleted": True}
    assert not db.record("gym_workout", "draft")
    assert db.record("gym_program", "program")
    assert db.record("gym_excel_history", "source")
    assert gym.history("synthetic") == []
    assert gym.update_workout("draft", gym.WorkoutUpdate(revision=2, sets={})) is None


def test_delete_refuses_stale_revision_completed_session_and_other_owner(workspace, monkeypatch):
    _, original = workspace
    with pytest.raises(gym.Conflict):
        gym.delete_workout("draft", 1)
    assert db.record("gym_workout", "draft") == original
    db.upsert_record("gym_workout", "draft", {**original, "finished_at": "2026-01-01T13:00:00Z"})
    with pytest.raises(gym.Conflict):
        gym.delete_workout("draft", 2)
    assert db.record("gym_workout", "draft")["finished_at"]
    monkeypatch.setattr(db, "user_id", lambda: "another-owner")
    assert gym.delete_workout("draft", 2) is None


def test_private_delete_endpoint_revision_and_not_found(workspace):
    path, _ = workspace
    write_secret(path / "app.json", {"access_key": "test-key"})
    api.sessions.clear()
    api.login_attempts.clear()
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        assert (
            client.request("DELETE", "/api/gym/workouts/draft", json={"revision": 2}).status_code
            == 401
        )
        assert client.post("/api/login", json={"access_key": "test-key"}).status_code == 200
        assert (
            client.request("DELETE", "/api/gym/workouts/draft", json={"revision": 0}).status_code
            == 422
        )
        assert (
            client.request("DELETE", "/api/gym/workouts/draft", json={"revision": 1}).status_code
            == 409
        )
        assert (
            client.request(
                "DELETE",
                "/api/gym/workouts/draft",
                json={"revision": 2},
                headers={"Origin": "https://untrusted.invalid"},
            ).status_code
            == 403
        )
        assert (
            client.request("DELETE", "/api/gym/workouts/draft", json={"revision": 2}).status_code
            == 200
        )
        assert client.get("/api/gym/workouts/draft").status_code == 404
        assert (
            client.request("DELETE", "/api/gym/workouts/draft", json={"revision": 2}).status_code
            == 404
        )
