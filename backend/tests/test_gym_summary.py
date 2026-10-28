"""Synthetic weekly review regressions; no private training or provider data."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from coach import api, db, exercise_catalog, gym_summary
from coach.config import user_scope
from coach.secrets import write_secret


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        exercise_catalog,
        "catalogue",
        lambda: {
            "repdb:synthetic": {
                "name": "Synthetic press",
                "muscles": ["Chest"],
                "muscles_secondary": ["Triceps", "Chest"],
            },
            "repdb:other": {
                "name": "Other movement",
                "muscles": ["Quads"],
                "muscles_secondary": [],
            },
        },
    )
    monkeypatch.setattr(exercise_catalog, "resolution", lambda *a, **kw: {"catalog_id": None})
    return tmp_path


def row(weight=20, reps=10, done=True, seconds=None):
    return {"weight": weight, "reps": reps, "done": done, "seconds": seconds}


def workout(
    key="w",
    started="2026-10-28T12:00:00Z",
    sets=None,
    catalog="repdb:synthetic",
    convention="total",
    context="",
    finished="2026-10-28T13:00:00Z",
):
    value = {
        "id": key,
        "title": "Synthetic workout",
        "started_at": started,
        "finished_at": finished,
        "exercises": [
            {
                "id": "row",
                "exercise_id": "synthetic",
                "name": "Synthetic movement",
                "catalog_id": catalog,
                "weight_convention": convention,
                "weight_context": context,
                "logged_sets": sets if sets is not None else [row()],
            }
        ],
    }
    db.upsert_record("gym_workout", key, value)
    return value


def activity(
    key="a", started="2026-10-28 12:10:00", duration=3600, sport="strength_training", **kwargs
):
    value = {
        "activityName": "Synthetic Garmin",
        "startTimeGMT": started,
        "duration": duration,
        "activityType": {"typeKey": sport},
        **kwargs,
    }
    db.upsert_record("activity", key, value)
    return value


def review(day="2026-10-28"):
    return gym_summary.weekly(date.fromisoformat(day))


def test_validated_only_unknowns_and_documented_muscles():
    workout(sets=[row(20, 10), row(100, 10, False), row(None, 8), row(None, None, True, 30)])
    data = review()
    assert data["totals"]["sets"] == 3
    assert data["totals"]["volume_kg"] == 200
    assert data["totals"]["unknown_load_sets"] == 2
    assert data["exercises"][0]["sets"][1]["weight"] is None
    assert data["muscles"] == [
        {"name": "Chest", "primary_sets": 3, "secondary_sets": 0},
        {"name": "Triceps", "primary_sets": 0, "secondary_sets": 3},
    ]
    assert data["totals"]["duration_seconds"] == 3600


def test_unresolved_and_unfinished_are_explicit_not_zero():
    workout(catalog=None, sets=[row(None, 8)], finished=None)
    data = review()
    assert data["totals"]["unknown_muscle_sets"] == 1
    assert data["totals"]["volume_kg"] is None
    assert data["totals"]["duration_seconds"] is None
    assert data["totals"]["missing_duration_sessions"] == 1
    assert data["sessions"][0]["finished"] is False
    assert data["muscles"] == []


def test_pairing_deduplicates_duration_and_preserves_missing_hr():
    workout()
    activity(duration=2500, averageHR=123)
    activity("run", sport="running")
    data = review()
    assert data["totals"]["sessions"] == data["totals"]["linked_sessions"] == 1
    assert data["totals"]["duration_seconds"] == 2500
    assert data["sessions"][0]["garmin"]["average_hr"] == 123
    assert data["sessions"][0]["garmin"]["max_hr"] is None
    assert not data["unmatched_garmin"]
    assert len(data["garmin_choices"]) == 1


def test_ambiguous_pairs_are_never_silently_chosen():
    workout()
    activity()
    activity("b", started="2026-10-28 12:20:00")
    data = review()
    assert data["totals"]["sessions"] == 3
    assert data["totals"]["linked_sessions"] == 0
    gym_summary.set_link("w", gym_summary.GarminLink(activity_id="b"))
    data = review()
    assert data["totals"]["sessions"] == 2
    assert data["sessions"][0]["garmin"]["id"] == "b"
    assert data["sessions"][0]["match_method"] == "manual"
    gym_summary.set_link("w", gym_summary.GarminLink())
    assert review()["totals"]["linked_sessions"] == 0
    assert review()["sessions"][0]["match_method"] == "separate"


def test_competing_workouts_and_duplicate_manual_links():
    workout("w1")
    workout("w2")
    activity()
    assert review()["totals"]["linked_sessions"] == 0
    gym_summary.set_link("w1", gym_summary.GarminLink(activity_id="a"))
    with pytest.raises(ValueError, match="déjà associée"):
        gym_summary.set_link("w2", gym_summary.GarminLink(activity_id="a"))
    assert review()["totals"]["sessions"] == 2
    gym_summary.set_link("w1", gym_summary.GarminLink(automatic=True))
    assert not db.record("gym_garmin_link", "w1")


def test_progression_is_rep_specific_latest_reference_and_all_time_record():
    workout("old", "2026-10-10T12:00:00Z", [row(30, 10)])
    workout("previous", "2026-10-20T12:00:00Z", [row(20, 10), row(22, 10), row(45, 5)])
    workout(sets=[row(25, 10), row(40, 5), row(10, 12)])
    progression = {p["reps"]: p for p in review()["exercises"][0]["progression"]}
    assert progression[10]["previous_weight"] == 22
    assert progression[10]["delta_kg"] == 3
    assert progression[10]["record"] is False
    assert progression[5]["delta_kg"] == -5
    assert progression[12]["previous_weight"] is None
    workout(sets=[row(35, 10)])
    assert review()["exercises"][0]["progression"][0]["record"] is True


def test_variant_context_convention_do_not_pool():
    workout("old", "2026-10-20T12:00:00Z", [row(100)], convention="per_dumbbell")
    workout("other", "2026-10-28T10:00:00Z", [row(25)], catalog="repdb:other")
    workout()
    data = review()
    assert len(data["exercises"]) == 2
    assert all(p["previous_weight"] is None for e in data["exercises"] for p in e["progression"])
    workout("old-context", "2026-10-21T12:00:00Z", context="another machine")
    assert review()["exercises"][0]["progression"][0]["previous_weight"] is None
    assert {m["name"] for m in review()["muscles"]} == {"Chest", "Triceps", "Quads"}


def test_local_week_boundary_and_dst_and_no_pagination():
    # Sunday 23:30 UTC = Monday 00:30 Paris after the DST switch.
    workout("edge", "2026-10-25T23:30:00Z", finished=None)
    activity(started="2026-10-25 23:35:00")
    assert review()["totals"]["sessions"] == 1
    assert review()["totals"]["linked_sessions"] == 1
    assert review("2026-10-25")["totals"]["sessions"] == 0
    for i in range(55):
        workout(f"more-{i}", "2026-10-29T12:00:00Z", finished=None)
    assert review()["totals"]["sets"] == 56
    assert len(review()["sessions"]) == 56


def test_empty_workouts_excluded_garmin_missing_duration_and_owner_isolation():
    workout(sets=[row(done=False)])
    activity(duration=None)
    assert review()["totals"]["sessions"] == 1
    assert review()["totals"]["sets"] == 0
    assert review()["totals"]["duration_seconds"] is None
    with user_scope("another-owner"):
        assert review()["totals"]["sessions"] == 0
        assert gym_summary.set_link("w", gym_summary.GarminLink(activity_id="a")) is None
        workout("foreign")
        with pytest.raises(ValueError, match="introuvable"):
            gym_summary.set_link("foreign", gym_summary.GarminLink(activity_id="a"))
    assert review()["totals"]["sets"] == 0


def test_routes_require_session_and_validate_links(workspace):
    write_secret(workspace / "app.json", {"access_key": "synthetic-test-key"})
    api.sessions.clear()
    api.session_owners.clear()
    api.login_attempts.clear()
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        assert client.get("/api/gym/summary").status_code == 401
        assert (
            client.put("/api/gym/workouts/w/garmin", json={"activity_id": "a"}).status_code == 401
        )
        assert (
            client.post("/api/login", json={"access_key": "synthetic-test-key"}).status_code == 200
        )
        workout()
        activity()
        assert client.get("/api/gym/summary?week=2026-10-28").json()["totals"]["sessions"] == 1
        assert client.get("/api/gym/summary?week=invalid").status_code == 422
        assert (
            client.put("/api/gym/workouts/w/garmin", json={"activity_id": "a"}).status_code == 200
        )
        assert (
            client.put("/api/gym/workouts/missing/garmin", json={"activity_id": "a"}).status_code
            == 404
        )
        activity("run", sport="running")
        assert (
            client.put("/api/gym/workouts/w/garmin", json={"activity_id": "run"}).status_code == 422
        )


def test_deleted_workout_does_not_reserve_garmin_forever():
    workout("deleted")
    workout("kept")
    activity()
    gym_summary.set_link("deleted", gym_summary.GarminLink(activity_id="a"))
    db.delete_record("gym_workout", "deleted")
    gym_summary.set_link("kept", gym_summary.GarminLink(activity_id="a"))
    assert review()["sessions"][0]["garmin"]["id"] == "a"
    assert review()["totals"]["sessions"] == 1
