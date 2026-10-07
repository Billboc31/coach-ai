import pytest
from garminconnect import GarminConnectConnectionError, GarminConnectTooManyRequestsError

from coach import db, garmin


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Mobile login: HTTP 403 token=private-secret", "403"),
        ("request timed out private-secret", "Délai"),
        ("Could not resolve host private-secret", "DNS"),
        ("certificate verify failed private-secret", "TLS"),
        ("All login strategies exhausted private-secret", "non déterminée"),
    ],
)
def test_connection_diagnostic_never_exposes_upstream(message, expected):
    result = garmin.safe_failure(GarminConnectConnectionError(message))
    assert expected in result
    assert "private-secret" not in result


def test_login_failure_reports_progress_without_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("builtins.input", lambda _: "athlete@example.invalid")
    monkeypatch.setattr(garmin, "getpass", lambda _: "private-password")
    clients = []

    class Fake:
        def __init__(self, **kwargs):
            self.password = kwargs.get("password")
            clients.append(self)

        def login(self, path):
            raise GarminConnectConnectionError("HTTP 403 private-password")

    monkeypatch.setattr(garmin, "Garmin", Fake)
    with pytest.raises(ValueError, match="403"):
        garmin.authenticate(reauth=True)
    assert clients[0].password is None
    assert "en cours" in capsys.readouterr().out


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
