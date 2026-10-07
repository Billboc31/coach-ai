import json

import pytest
from fastapi.testclient import TestClient

from coach import api, db
from coach.secrets import write_secret


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    api.sessions.clear()
    api.login_attempts.clear()
    write_secret(tmp_path / "app.json", {"access_key": "private-test-key"})
    with TestClient(api.app, headers={"Origin": "http://127.0.0.1:5173"}) as c:
        yield c


def unlock(client):
    response = client.post("/api/login", json={"access_key": "private-test-key"})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]


def test_private_routes_and_cross_origin(client):
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/health").status_code == 200
    assert (
        client.post(
            "/api/login",
            json={"access_key": "private-test-key"},
            headers={"Origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    unlock(client)
    assert client.get("/api/dashboard").status_code == 200
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/dashboard").status_code == 401


def test_bruteforce_limit(client):
    for _ in range(5):
        assert client.post("/api/login", json={"access_key": "wrong"}).status_code == 401
    assert client.post("/api/login", json={"access_key": "wrong"}).status_code == 429


def test_profile_notes_persistence_and_timezone(client):
    unlock(client)
    profile = {
        "name": "Athlète",
        "timezone": "Europe/Paris",
        "goals": "Marathon",
        "constraints": "Tennis jeudi",
        "sports": ["Course", "Tennis"],
    }
    assert client.put("/api/profile", json=profile).status_code == 200
    assert client.post("/api/notes", json={"content": "Fatigue aujourd’hui"}).status_code == 200
    assert client.post("/api/notes", json={"content": "  "}).status_code == 422
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["profile"] == profile
    assert dashboard["notes"][0]["content"] == "Fatigue aujourd’hui"
    assert "+00:00" in dashboard["notes"][0]["created_at"]
    assert client.put("/api/profile", json={**profile, "timezone": "Bad/Zone"}).status_code == 422


def test_status_never_exposes_provider_tokens(client, tmp_path):
    write_secret(
        tmp_path / "chatgpt.json",
        {
            "access_token": "provider-secret",
            "refresh_token": "refresh-secret",
            "scope": "chatgpt.tokens.use.direct",
        },
    )
    unlock(client)
    response = client.get("/api/dashboard")
    assert response.json()["integrations"]["chatgpt"]["configured"] is True
    assert "provider-secret" not in response.text
    assert "refresh-secret" not in response.text
    assert "private-test-key" not in response.text


def test_upsert_idempotent_and_user_scoped(client, monkeypatch):
    db.upsert_record("activity", "123", {"distance": 1000})
    db.upsert_record("activity", "123", {"distance": 2000})
    assert len(db.records("activity")) == 1
    assert db.records("activity")[0]["data"]["distance"] == 2000
    monkeypatch.setattr(db, "user_id", lambda: "another-user")
    assert db.records("activity") == []
    assert db.history("notes") == []


def test_context_minimizes_data_and_preserves_missing_measure(client):
    db.upsert_record(
        "activity",
        "123",
        {
            "activityName": "Run",
            "startLatitude": 42,
            "startTimeGMT": "2026-10-01 10:00:00",
            "distance": 1000,
        },
    )
    db.upsert_record("health", "2026-10-01", {"summary": {"totalSteps": 200}})
    context = api.coach_context()
    assert "startLatitude" not in json.dumps(context)
    assert context["recovery"][0]["resting_hr"] is None
    assert context["recovery"][0]["sleep_seconds"] is None


def test_failed_chat_is_not_saved(client, monkeypatch):
    unlock(client)

    def fail(*args):
        raise ValueError("Réponse incomplète")

    monkeypatch.setattr(api.chatgpt, "respond", fail)
    assert (
        client.post("/api/chat", json={"content": "Séance demain ?", "model": "test"}).status_code
        == 503
    )
    assert db.history("messages") == []
    assert not api.chat_lock.locked()


def test_successful_chat_persists_context_and_usage(client, monkeypatch):
    unlock(client)

    def respond(model, context, messages):
        assert messages[-1]["content"] == "Séance demain ?"
        assert "as_of" in context
        return "Dis-moi tes disponibilités.", {"input_tokens": 100}

    monkeypatch.setattr(api.chatgpt, "respond", respond)
    assert (
        client.post("/api/chat", json={"content": "Séance demain ?", "model": "test"}).status_code
        == 200
    )
    assert [m["role"] for m in db.history("messages")] == ["user", "assistant"]
    assert db.records("integration")[0]["data"]["usage"]["input_tokens"] == 100
