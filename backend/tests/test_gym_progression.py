import pytest
from pydantic import ValidationError

from coach import db, gym


@pytest.fixture
def workout(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    db.upsert_record("gym_program", "program", {"id": "program", "display_version": 2, "days": []})
    value = {
        "id": "session",
        "program_id": "program",
        "title": "Synthetic session",
        "revision": 1,
        "display_version": 2,
        "suggestions_applied": True,
        "started_at": "2026-01-01T12:00:00Z",
        "finished_at": None,
        "exercises": [
            {
                "id": "row",
                "exercise_id": "synthetic",
                "name": "Synthetic",
                "sets": 3,
                "reps": "10",
                "logged_sets": [
                    {"weight": weight, "reps": 10, "seconds": None, "done": True}
                    for weight in [10, 20, None]
                ],
            }
        ],
    }
    db.upsert_record("gym_workout", value["id"], value)
    return value


def test_explicit_increase_preserves_actuals_and_prefills_known_rows(workout):
    sets = {"row": workout["exercises"][0]["logged_sets"]}
    saved = gym.update_workout(
        "session", gym.WorkoutUpdate(revision=1, sets=sets, progression={"row": 2.5})
    )
    assert saved["exercises"][0]["logged_sets"] == sets["row"]
    reference = gym.history("synthetic")[0]
    suggested = gym.planned_logs({"sets": 3, "reps": "10"}, reference)
    assert [s["weight"] for s in suggested] == [12.5, 22.5, None]
    assert all(not s["done"] for s in suggested)
    saved = gym.update_workout(
        "session", gym.WorkoutUpdate(revision=2, sets=sets, progression={"row": 0})
    )
    assert saved["exercises"][0]["next_load_increase_kg"] == 0


def test_progression_validation_revision_and_incomplete_series(workout):
    sets = {"row": workout["exercises"][0]["logged_sets"]}
    for value in [-1, float("nan"), float("inf"), 2001]:
        with pytest.raises(ValidationError):
            gym.WorkoutUpdate(revision=1, sets=sets, progression={"row": value})
    with pytest.raises(gym.Conflict):
        gym.update_workout(
            "session", gym.WorkoutUpdate(revision=2, sets=sets, progression={"row": 1})
        )
    with pytest.raises(ValueError):
        gym.update_workout(
            "session", gym.WorkoutUpdate(revision=1, sets=sets, progression={"foreign": 1})
        )
    sets["row"][0]["done"] = False
    with pytest.raises(ValueError):
        gym.update_workout(
            "session", gym.WorkoutUpdate(revision=1, sets=sets, progression={"row": 1})
        )
    assert db.record("gym_workout", "session")["revision"] == 1
