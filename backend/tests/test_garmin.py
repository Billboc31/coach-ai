import pytest
from garminconnect import GarminConnectTooManyRequestsError

from coach import db, garmin


def test_sync_deduplicates_activities_and_retains_unavailable_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))

    class Fake:
        def login(self, path):
            pass

        def get_activities(self, *_):
            return [{"activityId": 123, "distance": 1000}]

        def get_user_summary(self, day):
            return {"totalSteps": 42}

        def get_sleep_data(self, day):
            raise RuntimeError("sensitive-upstream-detail")

        def get_heart_rates(self, day):
            return {"restingHeartRate": 50}

        def get_hrv_data(self, day):
            return None

        def get_training_readiness(self, day):
            return []

    monkeypatch.setattr(garmin, "Garmin", Fake)
    first = garmin.sync(1)
    day = db.records("health")[0]["key"]
    db.upsert_record("health", day, {"sleep": {"dailySleepDTO": {"sleepTimeSeconds": 100}}})
    second = garmin.sync(1)
    assert len(db.records("activity")) == 1
    assert second["activities"] == 1
    assert db.records("health")[0]["data"]["sleep"]["dailySleepDTO"]["sleepTimeSeconds"] == 100
    assert first["errors"][0]["type"] == "RuntimeError"
    assert "sensitive" not in str(second)


def test_rate_limit_stops_sync(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))

    class Fake:
        def login(self, path):
            raise GarminConnectTooManyRequestsError()

    monkeypatch.setattr(garmin, "Garmin", Fake)
    with pytest.raises(GarminConnectTooManyRequestsError):
        garmin.sync(1)
    assert db.records("integration") == []
