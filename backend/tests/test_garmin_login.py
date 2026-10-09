import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coach import api, garmin_login
from coach.config import data_dir, user_id, user_scope
from coach.secrets import read_secret, write_secret

ORIGIN = {"Origin": "http://localhost:8000"}
PASSWORD = "synthetic-password-never-store"
TOKEN = {"di_token": "new-token", "di_refresh_token": "new-refresh", "di_client_id": "new-client"}
OLD = {"di_token": "old-token", "di_refresh_token": "old-refresh", "di_client_id": "old-client"}


class FakeGarmin:
    owners = []

    def __init__(self, email, password, prompt_mfa, retry_attempts):
        assert password == PASSWORD
        assert retry_attempts == 0
        self.email, self.password, self.prompt_mfa = email, password, prompt_mfa
        self.client = self
        self.owners.append(user_id())

    def login(self, folder):
        assert self.skip_strategies == {
            "mobile+cffi",
            "widget+cffi",
            "portal+cffi",
            "portal+requests",
        }
        # A staged file must never leak into the active session on refusal/cancel.
        self.dump(folder)
        if self.email.startswith("mfa"):
            if self.prompt_mfa() != "123456":
                raise RuntimeError("HTTP 403 " + PASSWORD)
        if self.email.startswith("refused"):
            raise RuntimeError("HTTP 403 " + PASSWORD + " " + self.email)

    def get_user_summary(self, day):
        if self.email.startswith("verify-fail"):
            raise RuntimeError("HTTP 403 " + PASSWORD)
        return {}

    def dump(self, folder):
        write_secret(Path(folder) / "garmin_tokens.json", TOKEN)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("COACH_ACCESS_KEY", raising=False)
    write_secret(tmp_path / "app.json", {"access_key": "synthetic-owner-key"})
    api.sessions.clear()
    api.session_owners.clear()
    api.login_attempts.clear()
    FakeGarmin.owners = []
    monkeypatch.setattr(garmin_login, "Garmin", FakeGarmin)
    with TestClient(api.app, headers=ORIGIN) as value:
        assert (
            value.post("/api/login", json={"access_key": "synthetic-owner-key"}).status_code == 200
        )
        yield value


def begin(client, email="success@example.invalid"):
    return client.post("/api/garmin/login", json={"email": email, "password": PASSWORD})


def wait(client, wanted):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        value = client.get("/api/garmin/login").json()
        if value["status"] in wanted:
            return value
        time.sleep(0.01)
    pytest.fail("Login did not reach expected state")


def unlocked():
    until = time.monotonic() + 2
    while api.sync_lock.locked() and time.monotonic() < until:
        time.sleep(0.01)
    assert not api.sync_lock.locked()


def test_direct_login_validates_before_save_and_never_returns_secrets(client, tmp_path):
    response = begin(client)
    assert response.status_code == 202
    value = wait(client, {"completed"})
    unlocked()
    assert read_secret(tmp_path / "garmin" / "garmin_tokens.json") == TOKEN
    assert PASSWORD not in str(value) and "new-refresh" not in str(value)
    assert not list(tmp_path.glob("garmin-login-*"))
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert PASSWORD.encode() not in path.read_bytes()


@pytest.mark.parametrize("email", ["refused@example.invalid", "verify-fail@example.invalid"])
def test_refusal_preserves_previous_session_and_sanitizes_provider_error(client, tmp_path, email):
    path = tmp_path / "garmin" / "garmin_tokens.json"
    write_secret(path, OLD)
    assert begin(client, email).status_code == 202
    value = wait(client, {"failed"})
    unlocked()
    assert "403" in value["message"]
    assert PASSWORD not in str(value) and email not in str(value)
    assert read_secret(path) == OLD
    assert not list(tmp_path.glob("garmin-login-*"))


def test_mfa_duplicate_code_attempt_id_and_import_lock(client, tmp_path):
    assert begin(client, "mfa@example.invalid").status_code == 202
    attempt = wait(client, {"awaiting_mfa"})
    assert begin(client).status_code == 409
    assert client.post("/api/garmin/session", json=TOKEN).status_code == 409
    assert (
        client.post("/api/garmin/login/mfa", json={"id": "wrong", "code": "123456"}).status_code
        == 409
    )
    assert not (tmp_path / "garmin" / "garmin_tokens.json").exists()
    payload = {"id": attempt["id"], "code": "123456"}
    assert client.post("/api/garmin/login/mfa", json=payload).status_code == 200
    wait(client, {"completed"})
    assert client.post("/api/garmin/login/mfa", json=payload).status_code == 409
    unlocked()


def test_cancel_and_expiration_wake_mfa_and_preserve_old_session(client, tmp_path, monkeypatch):
    path = tmp_path / "garmin" / "garmin_tokens.json"
    write_secret(path, OLD)
    begin(client, "mfa@example.invalid")
    attempt = wait(client, {"awaiting_mfa"})
    assert client.post("/api/garmin/login/cancel", json={"id": attempt["id"]}).status_code == 200
    wait(client, {"cancelled"})
    unlocked()
    assert read_secret(path) == OLD
    monkeypatch.setattr(garmin_login, "TTL", 0.05)
    begin(client, "mfa@example.invalid")
    wait(client, {"expired", "cancelled"})
    unlocked()
    assert read_secret(path) == OLD
    assert not list(tmp_path.glob("garmin-login-*"))


def test_private_origin_validation_and_rate_limit_without_echo(client):
    anonymous = TestClient(api.app, headers=ORIGIN)
    assert begin(anonymous).status_code == 401
    for path in ["", "/mfa", "/cancel"]:
        assert (
            client.post(
                "/api/garmin/login" + path, headers={"Origin": "https://invalid.example"}, json={}
            ).status_code
            == 403
        )
    for payload in [
        {"email": "invalid", "password": PASSWORD},
        [],
        {"email": 42, "password": PASSWORD},
    ]:
        response = client.post("/api/garmin/login", json=payload)
        assert response.status_code == 422 and PASSWORD not in response.text
    invalid = client.post("/api/garmin/login/mfa", json={"id": "test", "code": PASSWORD})
    assert invalid.status_code == 422 and PASSWORD not in invalid.text
    for _ in range(3):
        assert begin(client, "refused@example.invalid").status_code == 202
        wait(client, {"failed"})
        unlocked()
    assert begin(client).status_code == 429


def test_members_have_private_attempts_workers_and_locks(client, tmp_path):
    invite = client.post("/api/invitations", json={"label": "Synthetic"}).json()
    member = TestClient(api.app, headers=ORIGIN)
    account = member.post(
        "/api/register", json={"name": "Sam", "invite_key": invite["invite_key"]}
    ).json()
    begin(client, "mfa@example.invalid")
    owner_attempt = wait(client, {"awaiting_mfa"})
    assert member.get("/api/garmin/login").json() == {"status": "idle"}
    assert (
        member.post("/api/garmin/login/cancel", json={"id": owner_attempt["id"]}).status_code == 409
    )
    assert begin(member).status_code == 202
    wait(member, {"completed"})
    assert FakeGarmin.owners == ["local", account["id"]]
    with user_scope(account["id"]):
        assert read_secret(data_dir() / "garmin" / "garmin_tokens.json") == TOKEN
        unlocked()
    assert not (tmp_path / "garmin" / "garmin_tokens.json").exists()
    client.post("/api/garmin/login/cancel", json={"id": owner_attempt["id"]})
    wait(client, {"cancelled"})
    unlocked()


def test_cancel_during_provider_request_cannot_commit_afterward(client, tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def slow_summary(self, day):
        entered.set()
        assert release.wait(3)
        return {}

    monkeypatch.setattr(FakeGarmin, "get_user_summary", slow_summary)
    write_secret(tmp_path / "garmin" / "garmin_tokens.json", OLD)
    attempt = begin(client).json()
    assert entered.wait(3)
    try:
        assert (
            client.post("/api/garmin/login/cancel", json={"id": attempt["id"]}).status_code == 200
        )
    finally:
        release.set()
    wait(client, {"cancelled"})
    unlocked()
    assert read_secret(tmp_path / "garmin" / "garmin_tokens.json") == OLD
