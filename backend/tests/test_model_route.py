"""Regressions for owner-scoped model loading, without any provider request."""

import pytest
from fastapi.testclient import TestClient

from coach import api, chatgpt
from coach.config import user_scope
from coach.secrets import write_secret


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    api.sessions.clear()
    api.login_attempts.clear()
    write_secret(tmp_path / "app.json", {"access_key": "test-key"})
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        client.post("/api/login", json={"access_key": "test-key"})
        yield client


def test_models_load_after_successful_recovery(client, monkeypatch):
    choices = [{"id": "test-sol", "name": "Test Sol"}]
    calls = []
    monkeypatch.setattr(chatgpt, "recover_session", lambda: choices)
    monkeypatch.setattr(chatgpt, "models", lambda: calls.append("models") or choices)
    assert client.post("/api/chatgpt/recover").json()["models"] == choices
    response = client.get("/api/models")
    assert response.status_code == 200, response.text
    assert response.json() == choices
    assert calls == ["models"]
    assert not api.chat_lock.locked()


def test_model_route_busy_lock_and_other_owner_isolation(client, monkeypatch):
    calls = []
    monkeypatch.setattr(chatgpt, "models", lambda: calls.append("models") or [])
    api.chat_lock.acquire()
    try:
        response = client.get("/api/models")
        assert response.status_code == 409
        assert calls == [] and api.chat_lock.locked()
    finally:
        api.chat_lock.release()
    with user_scope("other-test-owner"):
        api.chat_lock.acquire()
    try:
        assert client.get("/api/models").status_code == 200
        with user_scope("other-test-owner"):
            assert api.chat_lock.locked()
    finally:
        with user_scope("other-test-owner"):
            api.chat_lock.release()


@pytest.mark.parametrize("typed", [True, False])
def test_model_route_failure_releases_lock(client, monkeypatch, typed):
    def unavailable():
        if typed:
            raise chatgpt.ConnectionError("Limite ChatGPT atteinte", "limit", 429)
        raise RuntimeError("private-provider-body")

    monkeypatch.setattr(chatgpt, "models", unavailable)
    response = client.get("/api/models")
    assert response.status_code == (429 if typed else 503)
    assert "private-provider-body" not in response.text
    assert not api.chat_lock.locked()


def test_model_route_requires_app_session(client):
    client.cookies.clear()
    assert client.get("/api/models").status_code == 401
