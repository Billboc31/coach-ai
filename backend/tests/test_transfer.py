from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from garminconnect import GarminConnectConnectionError

from coach import api, garmin, transfer
from coach.secrets import read_secret, write_secret

TOKENS = {
    "di_token": "fake-access",
    "di_refresh_token": "fake-refresh",
    "di_client_id": "fake-client",
}


def test_import_validates_and_saves_rotated_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    target = Path(garmin.session_path()) / "garmin_tokens.json"
    write_secret(target, {**TOKENS, "di_token": "previous"})

    class Fake:
        def __init__(self):
            self.client = self

        def login(self, folder):
            assert read_secret(Path(folder) / "garmin_tokens.json") == TOKENS

        def get_user_summary(self, day):
            return {}

        def dump(self, folder):
            write_secret(Path(folder) / "garmin_tokens.json", {**TOKENS, "di_token": "rotated"})

    monkeypatch.setattr(garmin, "Garmin", Fake)
    garmin.import_session(TOKENS)
    assert read_secret(target)["di_token"] == "rotated"
    assert target.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob("garmin-check-*"))


def test_failed_import_keeps_existing_session(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    target = Path(garmin.session_path()) / "garmin_tokens.json"
    previous = {**TOKENS, "di_token": "previous"}
    write_secret(target, previous)

    class Fake:
        def login(self, folder):
            raise GarminConnectConnectionError("HTTP 403 private-upstream-body")

    monkeypatch.setattr(garmin, "Garmin", Fake)
    with pytest.raises(GarminConnectConnectionError):
        garmin.import_session(TOKENS)
    assert read_secret(target) == previous
    assert not list(tmp_path.glob("garmin-check-*"))


def test_upload_requires_auth_origin_and_never_echoes_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    api.sessions.clear()
    api.login_attempts.clear()
    write_secret(tmp_path / "app.json", {"access_key": "test-key"})
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        assert client.post("/api/garmin/session", json=TOKENS).status_code == 401
        client.post("/api/login", json={"access_key": "test-key"})
        assert (
            client.post(
                "/api/garmin/session", json=TOKENS, headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        response = client.post("/api/garmin/session", json={**TOKENS, "password": "secret"})
        assert response.status_code == 422
        assert "fake-access" not in response.text
        response = client.post("/api/garmin/session", content=b"x" * 65537)
        assert response.status_code == 413

        def fail(value):
            raise GarminConnectConnectionError("HTTP 403 private-upstream-body")

        monkeypatch.setattr(garmin, "import_session", fail)
        response = client.post("/api/garmin/session", json=TOKENS)
        assert response.status_code == 502
        assert "403" in response.json()["detail"]
        assert "private-upstream-body" not in response.text
        assert not api.sync_lock.locked()
        monkeypatch.setattr(garmin, "import_session", lambda value: None)
        assert client.post("/api/garmin/session", json=TOKENS).json() == {"ok": True}


def test_transfer_sends_only_to_https_owner_and_syncs(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    write_secret(Path(garmin.session_path()) / "garmin_tokens.json", TOKENS)
    monkeypatch.setattr("builtins.input", lambda _: "https://coach.example")
    monkeypatch.setattr(transfer, "getpass", lambda _: "private-key")
    actual_client = httpx.Client
    calls = []

    def request(req):
        calls.append(req.url.path)
        assert req.url.host == "coach.example"
        assert req.headers["origin"] == "https://coach.example"
        if req.url.path == "/api/garmin/sync":
            return httpx.Response(200, json={"activities": 100, "days": 7})
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(
        transfer.httpx,
        "Client",
        lambda **kwargs: actual_client(**kwargs, transport=httpx.MockTransport(request)),
    )
    transfer.transfer()
    assert calls == ["/api/login", "/api/garmin/session", "/api/garmin/sync", "/api/logout"]
    output = capsys.readouterr().out
    assert "100 activités" in output
    assert "private-key" not in output
    assert "fake-access" not in output


@pytest.mark.parametrize(
    "url", ["http://coach.example", "https://user:pass@coach.example", "https://coach.example/path"]
)
def test_transfer_rejects_unsafe_destination(monkeypatch, tmp_path, url):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    write_secret(Path(garmin.session_path()) / "garmin_tokens.json", TOKENS)
    monkeypatch.setattr("builtins.input", lambda _: url)
    with pytest.raises(ValueError, match="HTTPS"):
        transfer.transfer()
