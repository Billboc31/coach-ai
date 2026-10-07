import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient
from garminconnect import GarminConnectConnectionError, GarminConnectTooManyRequestsError

from coach import api, db
from coach import garmin_jobs as jobs
from coach.garmin_lock import storage_lock
from coach.secrets import write_secret


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    jobs.stop.clear()
    monkeypatch.setattr(jobs, "spawn", lambda job, lock: None)
    yield tmp_path
    jobs.stop.clear()


def new_job(mode="all", start=None):
    lock = threading.Lock()
    job = jobs.launch(lock, mode=mode, start=start, end=date(2026, 10, 7))
    lock.release()
    return job


class Fake:
    def __init__(self):
        self.pages = []

    def login(self, path):
        pass

    def get_activities(self, offset, limit):
        self.pages.append(offset)
        if offset == 0:
            return [
                {
                    "activityId": i,
                    "startTimeLocal": "2026-10-07 10:00:00",
                    "duration": 3600,
                    "distance": 1000,
                    "activityType": {"typeKey": "running"},
                }
                for i in range(100)
            ]
        return [{"activityId": 100, "startTimeLocal": "2026-10-05 10:00:00"}]

    def __getattr__(self, name):
        if name.startswith("get_"):
            return lambda day: {"value": 1} if name == "get_user_summary" else None
        raise AttributeError(name)


def test_full_history_paginates_and_replay_deduplicates(workspace):
    job = new_job()
    client = Fake()
    jobs.run(job, client, pace=0)
    assert client.pages == [0, 100]
    assert job["start"] == "2026-10-05"
    assert job["total_days"] == job["days_processed"] == 3
    assert job["days_with_data"] == 3
    assert db.coverage("activity")["count"] == 101
    second = new_job()
    jobs.run(second, Fake(), pace=0)
    assert db.coverage("activity")["count"] == 101
    assert db.coverage("health")["count"] == 3
    assert (
        next(r for r in db.activity_months() if r["sport"] == "running")["duration_seconds"]
        == 360000
    )


def test_custom_range_filters_activity_dates(workspace):
    job = new_job("range", date(2026, 10, 7))
    jobs.run(job, Fake(), pace=0)
    assert db.coverage("activity")["count"] == 100
    assert job["days_processed"] == 1


def test_full_health_can_precede_first_activity(workspace):
    job = new_job(start=date(2026, 10, 4))
    jobs.run(job, Fake(), pace=0)
    assert job["total_days"] == 4
    assert db.coverage("health")["first"] == "2026-10-04"


def test_source_failure_preserves_old_value_and_tracks_freshness(workspace):
    db.upsert_record("health", "2026-10-07", {"sleep": {"old": 1}})

    class Partial(Fake):
        def get_sleep_data(self, day):
            raise RuntimeError("private-response")

    job = new_job("range", date(2026, 10, 7))
    jobs.run(job, Partial(), pace=0)
    saved = db.record("health", "2026-10-07")
    assert saved["sleep"] == {"old": 1}
    assert saved["_sources"]["sleep"]["status"] == "unavailable"
    assert "private-response" not in str(job)


def test_cancel_and_resume_checkpoints(workspace):
    job = new_job()

    class Cancel(Fake):
        def get_user_summary(self, day):
            jobs.stop.set()
            return {"steps": 42}

    jobs.run(job, Cancel(), pace=0)
    assert job["phase"] == "health"
    assert job["days_processed"] == 0
    jobs.stop.clear()
    jobs.run(job, Fake(), pace=0)
    assert job["days_processed"] == 3
    assert db.coverage("activity")["count"] == 101


def test_worker_stops_on_http403_and_releases_lock(workspace, monkeypatch):
    class Refused(Fake):
        def login(self, path):
            raise GarminConnectConnectionError("HTTP 403 private-body")

    monkeypatch.setattr(jobs, "Garmin", Refused)
    job = new_job()
    lock = threading.Lock()
    lock.acquire()
    jobs.worker(job, lock)
    assert not lock.locked()
    assert jobs.status()["status"] == "failed"
    assert "403" in jobs.status()["error"]
    assert "private-body" not in str(jobs.status())


def test_rate_limit_backoff_is_bounded(workspace, monkeypatch):
    class Limited(Fake):
        def login(self, path):
            raise GarminConnectTooManyRequestsError()

    monkeypatch.setattr(jobs, "Garmin", Limited)
    waits = []
    monkeypatch.setattr(jobs.stop, "wait", lambda delay: waits.append(delay) or False)
    job = new_job()
    lock = threading.Lock()
    lock.acquire()
    jobs.worker(job, lock)
    assert waits == [60, 120, 240]
    assert jobs.status()["status"] == "paused"
    assert not lock.locked()


def test_recovery_and_exclusive_start(workspace, monkeypatch):
    job = new_job()
    lock = threading.Lock()
    lock.acquire()
    with pytest.raises(ValueError, match="déjà"):
        jobs.launch(lock)
    lock.release()
    calls = []
    monkeypatch.setattr(jobs, "launch", lambda *args, **kwargs: calls.append(kwargs))
    jobs.recover(lock)
    assert calls == [{"resume": True}]
    assert jobs.status()["id"] == job["id"]


def test_cross_process_storage_guard(workspace):
    with storage_lock(), pytest.raises(ValueError, match="opération"):
        with storage_lock():
            pass


def test_repeated_page_stops_instead_of_looping(workspace):
    class Repeated(Fake):
        def get_activities(self, offset, limit):
            return super().get_activities(0, limit)

    with pytest.raises(ValueError, match="repeated"):
        jobs.run(new_job(), Repeated(), pace=0)
    assert db.coverage("activity")["count"] == 100


def test_context_does_not_treat_retained_sleep_as_fresh(workspace):
    db.upsert_record(
        "health",
        "2026-10-07",
        {
            "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 28800}},
            "_sources": {"sleep": {"status": "unavailable", "read_at": db.now()}},
        },
    )
    assert api.coach_context()["recovery"][0]["sleep_seconds"] is None


def test_job_api_validation_and_activity_pagination(workspace):
    api.sessions.clear()
    api.login_attempts.clear()
    write_secret(workspace / "app.json", {"access_key": "test-key"})
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        assert client.get("/api/garmin/jobs").status_code == 401
        client.post("/api/login", json={"access_key": "test-key"})
        assert client.post("/api/garmin/jobs", json={"mode": "bad"}).status_code == 422
        assert (
            client.post(
                "/api/garmin/jobs", json={"start": "2026-10-07", "end": "2026-10-06"}
            ).status_code
            == 422
        )
        result = client.post("/api/garmin/jobs", json={"mode": "all"})
        try:
            assert result.status_code == 202
            assert client.get("/api/garmin/jobs").json()["id"] == result.json()["id"]
            assert client.post("/api/garmin/jobs", json={}).status_code == 409
        finally:
            api.sync_lock.release()
        assert client.get("/api/activities?offset=-1").status_code == 422
        for i in range(60):
            db.upsert_record("activity", str(i), {"startTimeGMT": "2026-10-07", "duration": i})
        page = client.get("/api/activities?offset=50").json()
        assert page["total"] == 60 and len(page["items"]) == 10
