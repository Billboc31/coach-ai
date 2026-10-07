import time
from dataclasses import replace
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from coach import api, chatgpt, transfer
from coach.secrets import read_secret, write_secret


@pytest.fixture
def credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    keys = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    )
    base = {"iss": chatgpt.ISSUER, "sub": "test-user", "iat": time.time() - 100}
    value = {
        "client_id": "issued",
        "subject": "test-user",
        "scope": chatgpt.SCOPES,
        "access_token": jwt.encode(
            {
                **base,
                "aud": chatgpt.RESOURCE,
                "exp": time.time() + 600,
                "client_id": "issued",
                "scope": chatgpt.SCOPES,
            },
            private,
            algorithm="RS256",
        ),
        "id_token": jwt.encode(
            {**base, "aud": "issued", "exp": time.time() - 30}, private, algorithm="RS256"
        ),
        "refresh_token": "private-refresh",
        "expires_at": time.time() + 600,
    }
    monkeypatch.setattr(chatgpt, "catalogue", lambda _: [{"id": "test-model", "name": "Test"}])
    return tmp_path, value, keys


def test_import_verifies_retained_identity_and_preserves_host(credentials):
    folder, value, keys = credentials
    write_secret(folder / "host.json", {"id": "runtime-host"})
    chatgpt.import_session(value, keys)
    assert read_secret(folder / "host.json") == {"id": "runtime-host"}
    assert read_secret(chatgpt.credential_path())["subject"] == "test-user"
    assert chatgpt.credential_path().stat().st_mode & 0o777 == 0o600


def test_failed_import_preserves_previous_credentials(credentials, monkeypatch):
    _, value, keys = credentials
    previous = {**value, "refresh_token": "previous"}
    write_secret(chatgpt.credential_path(), previous)
    monkeypatch.setattr(chatgpt, "catalogue", lambda _: [])
    with pytest.raises(ValueError):
        chatgpt.import_session(value, keys)
    assert read_secret(chatgpt.credential_path()) == previous


def test_account_switch_and_mismatched_identity_rejected(credentials):
    _, value, keys = credentials
    with pytest.raises(ValueError):
        chatgpt.import_session({**value, "subject": "other"}, keys)
    write_secret(chatgpt.credential_path(), {**value, "subject": "existing"})
    with pytest.raises(ValueError):
        chatgpt.import_session(value, keys)


def test_invalid_access_signature_rejected(credentials):
    _, value, keys = credentials
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(value["access_token"], options={"verify_signature": False})
    with pytest.raises(jwt.InvalidSignatureError):
        chatgpt.import_session(
            {**value, "access_token": jwt.encode(claims, other, algorithm="RS256")}, keys
        )
    assert not chatgpt.credential_path().exists()


@pytest.mark.parametrize(
    "patch",
    [{"expires_at": 0}, {"expires_at": True}, {"scope": "openid"}, {"host_id": "copied-host"}],
)
def test_invalid_sessions_rejected(credentials, patch):
    _, value, _ = credentials
    with pytest.raises(ValueError):
        chatgpt.validate_session({**value, **patch})


def test_api_private_import_test_and_disconnect(credentials, monkeypatch):
    folder, value, _ = credentials
    api.sessions.clear()
    api.login_attempts.clear()
    write_secret(folder / "app.json", {"access_key": "test-key"})
    monkeypatch.setattr(chatgpt, "import_session", lambda _: [{"id": "test", "name": "Test"}])
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        assert client.post("/api/chatgpt/session", json=value).status_code == 401
        client.post("/api/login", json={"access_key": "test-key"})
        assert (
            client.post(
                "/api/chatgpt/session", json=value, headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        invalid = client.post("/api/chatgpt/session", json={**value, "password": "secret"})
        assert invalid.status_code == 422
        assert "private-refresh" not in invalid.text
        assert client.post("/api/chatgpt/session", content=b"x" * 65537).status_code == 413
        assert client.post("/api/chatgpt/session", json=value).status_code == 200
        api.chat_lock.acquire()
        try:
            assert client.post("/api/chatgpt/disconnect").status_code == 409
        finally:
            api.chat_lock.release()
        captured = []
        monkeypatch.setattr(chatgpt, "models", lambda: [{"id": "test", "name": "Test"}])
        monkeypatch.setattr(
            chatgpt,
            "respond",
            lambda model, context, messages: (captured.append(context) or "OK", {}),
        )
        assert client.post("/api/chatgpt/test").status_code == 200
        assert captured == [{}]
        monkeypatch.setattr(chatgpt, "respond", lambda *args: ("", {}))
        assert client.post("/api/chatgpt/test").status_code == 503
        write_secret(chatgpt.credential_path(), value)
        assert client.post("/api/chatgpt/disconnect").status_code == 200
        assert not chatgpt.credential_path().exists()
        assert not api.chat_lock.locked()


@pytest.mark.parametrize("status", [200, 502, 307])
def test_transfer_removes_local_only_after_server_success(credentials, monkeypatch, status):
    _, value, _ = credentials
    write_secret(chatgpt.credential_path(), value)
    monkeypatch.setattr(chatgpt, "access_token", lambda: value["access_token"])
    monkeypatch.setattr("builtins.input", lambda _: "https://coach.example")
    monkeypatch.setattr(transfer, "getpass", lambda _: "app-key")
    actual_client = httpx.Client
    calls = []

    def request(req):
        calls.append(req.url.path)
        assert req.url.host == "coach.example"
        if req.url.path == "/api/chatgpt/session":
            return httpx.Response(
                status, json={"ok": status == 200}, headers={"Location": "https://evil.example"}
            )
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(
        transfer.httpx,
        "Client",
        lambda **kwargs: actual_client(**kwargs, transport=httpx.MockTransport(request)),
    )
    if status == 200:
        transfer.transfer_chatgpt()
        assert not chatgpt.credential_path().exists()
    else:
        with pytest.raises(ValueError):
            transfer.transfer_chatgpt()
        assert read_secret(chatgpt.credential_path()) == value
    assert calls == ["/api/login", "/api/chatgpt/session", "/api/logout"]


def test_hosted_app_refuses_loopback_login(credentials, monkeypatch):
    folder, _, _ = credentials
    monkeypatch.setattr(api, "settings", replace(api.settings, production=True))
    api.sessions.clear()
    api.login_attempts.clear()
    write_secret(folder / "app.json", {"access_key": "test-key"})
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        client.cookies.set("coach_session", "test-session")
        api.sessions["test-session"] = time.time() + 60
        assert client.post("/api/chatgpt/login").status_code == 409
        assert client.get("/api/chatgpt/login").json() == {"status": "unavailable"}


@pytest.mark.parametrize("fail", [False, True])
def test_local_ui_authorization_completes_or_sanitizes_failure(credentials, monkeypatch, fail):
    folder, _, _ = credentials
    write_secret(folder / "app.json", {"access_key": "test-key"})
    api.sessions.clear()
    api.login_attempts.clear()

    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    def sign_in(on_authorization):
        on_authorization("https://auth.openai.com/test")
        if fail:
            raise RuntimeError("private-provider-body")

    monkeypatch.setattr(api.threading, "Thread", InlineThread)
    monkeypatch.setattr(chatgpt, "sign_in", sign_in)
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        assert client.post("/api/chatgpt/login").status_code == 401
        client.post("/api/login", json={"access_key": "test-key"})
        assert client.post("/api/chatgpt/login").status_code == 202
        response = client.get("/api/chatgpt/login")
        assert response.json()["status"] == ("failed" if fail else "completed")
        assert "url" not in response.json()
        assert "private-provider-body" not in response.text
        assert not api.chat_lock.locked()
