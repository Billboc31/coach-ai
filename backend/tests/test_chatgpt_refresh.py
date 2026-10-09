"""Renewal and recovery use fictitious credentials and a mock OAuth server."""

import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from coach import api, chatgpt
from coach.secrets import read_secret, write_secret


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    value = {
        "access_token": "old-access",
        "refresh_token": "old-refresh",
        "client_id": "issued-test",
        "subject": "fictional",
        "scope": chatgpt.SCOPES,
        "expires_at": time.time() - 10,
    }
    write_secret(chatgpt.credential_path(), value)
    return value


def mock_http(monkeypatch, handler):
    client = httpx.Client
    monkeypatch.setattr(
        chatgpt.httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(handler), **kw)
    )


def test_rotating_refresh_serialized_and_persisted(saved, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url == chatgpt.TOKEN_URL
        assert b"refresh_token=old-refresh" in request.content
        assert b"client_id=issued-test" in request.content
        assert b"scope=" not in request.content
        return httpx.Response(
            200,
            json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600},
        )

    mock_http(monkeypatch, handler)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: chatgpt.access_token(), range(2))) == ["new-access"] * 2
    assert len(calls) == 1
    assert read_secret(chatgpt.credential_path())["refresh_token"] == "new-refresh"
    assert chatgpt.credential_path().stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "status,body,kind",
    [
        (503, {"detail": "private-provider-content"}, "temporary"),
        (429, {"error": "private-provider-content"}, "limit"),
        (403, {"error": "unknown"}, "permission"),
        (400, {"error": "invalid_client"}, "configuration"),
        (200, {"access_token": "replacement-without-refresh", "expires_in": 3600}, "temporary"),
    ],
)
def test_nonterminal_failure_preserves_credentials(saved, monkeypatch, status, body, kind):
    mock_http(monkeypatch, lambda _: httpx.Response(status, json=body))
    with pytest.raises(chatgpt.ConnectionError) as caught:
        chatgpt.access_token()
    assert caught.value.kind == kind
    assert "private-provider-content" not in str(caught.value)
    assert read_secret(chatgpt.credential_path()) == saved


def test_network_failure_preserves_credentials(saved, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("private-network-details", request=request)

    mock_http(monkeypatch, handler)
    with pytest.raises(chatgpt.ConnectionError) as caught:
        chatgpt.access_token()
    assert "private-network-details" not in str(caught.value)
    assert read_secret(chatgpt.credential_path()) == saved


@pytest.mark.parametrize("code", ["invalid_grant", "refresh_token_reused"])
def test_confirmed_invalid_refresh_clears_tokens_retains_registration(saved, monkeypatch, code):
    mock_http(monkeypatch, lambda _: httpx.Response(400, json={"error": code}))
    with pytest.raises(chatgpt.ConnectionError) as caught:
        chatgpt.access_token()
    assert caught.value.kind == "reauthorize"
    remaining = read_secret(chatgpt.credential_path())
    assert remaining["client_id"] == saved["client_id"]
    assert remaining["subject"] == saved["subject"]
    assert "access_token" not in remaining and "refresh_token" not in remaining


def test_not_yet_refreshable_but_still_valid_token_is_usable(saved, monkeypatch):
    saved.update(expires_at=time.time() + 30, earliest_refresh_at=time.time() + 20)
    write_secret(chatgpt.credential_path(), saved)
    mock_http(monkeypatch, lambda _: pytest.fail("must not refresh prematurely"))
    assert chatgpt.access_token() == "old-access"


def test_recovery_renews_once_after_catalogue_rejection(saved, monkeypatch):
    saved["expires_at"] = time.time() + 3600
    write_secret(chatgpt.credential_path(), saved)
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 3600,
                },
            )
        if request.headers["authorization"] == "Bearer old-access":
            return httpx.Response(401)
        return httpx.Response(
            200, json={"models": [{"slug": "test", "display_name": "Test", "visibility": "list"}]}
        )

    mock_http(monkeypatch, handler)
    assert chatgpt.recover_session() == [{"id": "test", "name": "Test"}]
    assert paths == ["/v1/models", "/api/accounts/oauth/token", "/v1/models"]


def test_recovery_does_not_loop_on_permission_or_renewed_rejection(saved, monkeypatch):
    saved["expires_at"] = time.time() + 3600
    write_secret(chatgpt.credential_path(), saved)
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(403)

    mock_http(monkeypatch, handler)
    with pytest.raises(chatgpt.ConnectionError):
        chatgpt.recover_session()
    assert calls == ["GET"]


def test_recovery_endpoint_auth_origin_safe_errors_and_lock(saved, monkeypatch):
    api.sessions.clear()
    api.login_attempts.clear()
    write_secret(chatgpt.credential_path().parent / "app.json", {"access_key": "test-key"})
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        assert client.post("/api/chatgpt/recover").status_code == 401
        client.post("/api/login", json={"access_key": "test-key"})
        assert (
            client.post(
                "/api/chatgpt/recover", headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        monkeypatch.setattr(chatgpt, "recover_session", lambda: [{"id": "test", "name": "Test"}])
        assert client.post("/api/chatgpt/recover").json()["ok"]
        api.chat_lock.acquire()
        try:
            assert client.post("/api/chatgpt/recover").status_code == 409
        finally:
            api.chat_lock.release()

        def unavailable():
            raise chatgpt.ConnectionError("Limite atteinte", "limit", 429)

        monkeypatch.setattr(chatgpt, "recover_session", unavailable)
        assert client.post("/api/chatgpt/recover").status_code == 429
        assert not api.chat_lock.locked()


def test_invalid_refresh_only_clears_selected_account(saved, monkeypatch):
    from coach.config import user_scope

    with user_scope("fictional-member"):
        write_secret(chatgpt.credential_path(), saved)
        mock_http(monkeypatch, lambda _: httpx.Response(400, json={"error": "invalid_grant"}))
        with pytest.raises(chatgpt.ConnectionError):
            chatgpt.access_token()
        assert not read_secret(chatgpt.credential_path()).get("access_token")
    assert read_secret(chatgpt.credential_path()) == saved


def test_recovery_does_not_refresh_twice_when_expired_token_already_rotated(saved, monkeypatch):
    methods = []

    def handler(request):
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 3600,
                },
            )
        return httpx.Response(401)

    mock_http(monkeypatch, handler)
    with pytest.raises(chatgpt.ConnectionError):
        chatgpt.recover_session()
    assert methods == ["POST", "GET"]
    assert read_secret(chatgpt.credential_path())["refresh_token"] == "new-refresh"
