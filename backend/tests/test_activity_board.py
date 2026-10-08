import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from coach import activities, api, db, garmin_jobs, garmin_schedule
from coach.secrets import write_secret


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(garmin_jobs, "spawn", lambda *args: None)
    return tmp_path


def due(workspace):
    write_secret(workspace / "garmin" / "garmin_tokens.json", {"test": True})
    instant = datetime(2026, 10, 7, 10, tzinfo=timezone.utc)
    db.upsert_record(
        "settings", "garmin_schedule", {"next_run": (instant - timedelta(minutes=1)).isoformat()}
    )
    return instant


def test_schedule_persists_and_does_not_replace_manual_checkpoint(workspace):
    instant = due(workspace)
    lock = threading.Lock()
    db.upsert_record(
        "sync_job",
        "garmin",
        {"id": "manual", "status": "paused", "phase": "health", "current_date": "2020-01-01"},
    )
    garmin_schedule.tick(lock, instant)
    assert garmin_jobs.status()["current_date"] == "2020-01-01"
    assert not lock.locked()
    garmin_schedule.configure(False, 30)
    assert garmin_schedule.state()["enabled"] is False
    assert garmin_schedule.state()["minutes"] == 30
    with pytest.raises(ValueError):
        garmin_schedule.configure(True, 1)


def test_automatic_launch_gap_catchup_and_failure_reactivation(workspace, monkeypatch):
    instant = due(workspace)
    lock = threading.Lock()
    db.upsert_record("integration", "garmin", {"synced_at": "2026-10-01T10:00:00+00:00"})
    garmin_schedule.tick(lock, instant)
    try:
        job = garmin_jobs.status()
        assert job["origin"] == "automatic" and job["start"] == "2026-09-29"
        assert job["end"] == "2026-10-07"
        assert garmin_schedule.state()["next_run"] == "2026-10-07T11:00:00+00:00"
        garmin_schedule.tick(lock, instant + timedelta(hours=2))
        assert garmin_jobs.status()["id"] == job["id"]
    finally:
        lock.release()
    job.update(status="failed", error="Authentification refusée.")
    garmin_jobs.save(job)
    garmin_schedule.tick(lock, instant + timedelta(minutes=1))
    assert not garmin_schedule.state()["enabled"]

    # Keep reactivation on the same simulated date, including when run near midnight.
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (instant + timedelta(minutes=1)).astimezone(tz)

    monkeypatch.setattr(garmin_schedule, "datetime", Clock)
    garmin_schedule.configure(True, 30)
    later = datetime.fromisoformat(garmin_schedule.state()["next_run"])
    garmin_schedule.tick(lock, later)
    try:
        assert garmin_jobs.status()["id"] != job["id"]
        assert garmin_schedule.state()["enabled"]
    finally:
        lock.release()


def test_activity_filters_null_totals_and_ownership(workspace, monkeypatch):
    db.upsert_record(
        "activity",
        "1",
        {
            "activityName": "Morning",
            "startTimeLocal": "2026-10-07",
            "activityType": {"typeKey": "trail_running"},
            "duration": 1200,
        },
    )
    db.upsert_record(
        "activity",
        "2",
        {
            "activityName": "Ride",
            "startTimeLocal": "2026-10-06",
            "activityType": {"typeKey": "cycling"},
            "duration": 3600,
            "distance": 10000,
        },
    )
    monkeypatch.setattr(db, "user_id", lambda: "another")
    db.upsert_record("activity", "3", {"activityName": "Private", "duration": 999})
    monkeypatch.setattr(db, "user_id", lambda: "local")
    from datetime import date

    page = activities.browse(sport="running", query="MORN", start=date(2026, 10, 7))
    assert page["total"] == 1 and page["totals"]["distance"] is None
    assert activities.details("3") is None
    assert activities.browse()["total"] == 2
    assert activities.browse(query="% OR 1=1")["total"] == 0


def test_detail_cache_safe_fields_and_preserved_on_failure(workspace, monkeypatch):
    db.upsert_record("activity", "1", {"duration": 100, "activityName": "Test"})

    class Fake:
        def login(self, path):
            pass

        def get_activity(self, key):
            return {"summaryDTO": {"duration": 120, "averageHR": 140, "startLatitude": 12}}

        def get_activity_details(self, key, **kwargs):
            assert kwargs == {"maxchart": 4000, "maxpoly": 0}
            return {"metricDescriptors": [], "activityDetailMetrics": []}

        def get_activity_splits(self, key):
            return {
                "lapDTOs": [{"lapIndex": 1, "duration": 120, "distance": 400, "startLatitude": 12}]
            }

    monkeypatch.setattr(activities, "Garmin", Fake)
    value = activities.refresh("1")
    assert value["data"]["duration"] == 120
    assert value["laps"][0]["distance"] == 400
    assert "startLatitude" not in str(value)

    def fail(*args):
        raise RuntimeError("provider-private-body")

    monkeypatch.setattr(Fake, "get_activity_splits", fail)
    with pytest.raises(RuntimeError):
        activities.refresh("1")
    assert activities.details("1") == value


def test_private_endpoints_and_detail_sync_conflict(workspace):
    write_secret(workspace / "app.json", {"access_key": "test-key"})
    api.sessions.clear()
    api.login_attempts.clear()
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        assert client.get("/api/garmin/schedule").status_code == 401
        assert client.get("/api/activities/1").status_code == 401
        client.post("/api/login", json={"access_key": "test-key"})
        assert (
            client.put("/api/garmin/schedule", json={"enabled": True, "minutes": 2}).status_code
            == 422
        )
        assert client.get("/api/activities?start=2026-10-07&end=2026-10-06").status_code == 422
        assert client.get("/api/activities/1").status_code == 404
        assert client.post("/api/activities/1/refresh").status_code == 404
        db.upsert_record("activity", "1", {"duration": 1})
        api.sync_lock.acquire()
        try:
            assert client.post("/api/activities/1/refresh").status_code == 409
            assert client.get("/api/activities/1").json()["data"]["duration"] == 1
        finally:
            api.sync_lock.release()
