import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from coach import api, chatgpt, db, planning
from coach.secrets import write_secret


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    api.sessions.clear()
    api.login_attempts.clear()
    write_secret(tmp_path / "app.json", {"access_key": "test-key"})
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as c:
        yield c


def unlock(c):
    assert c.post("/api/login", json={"access_key": "test-key"}).status_code == 200


def body():
    return {
        "title": "Séance exemple",
        "sport": "running",
        "day": datetime.now(ZoneInfo("Europe/Paris")).date().isoformat(),
        "time": "09:00",
        "duration_minutes": 30,
    }


def test_calendar_auth_validation_and_persisted_edits(client):
    data = body()
    assert client.get(f"/api/planning?start={data['day']}&end={data['day']}").status_code == 401
    assert client.post("/api/planning", json=data).status_code == 401
    unlock(client)
    assert client.post("/api/planning", json={**data, "time": "9:00"}).status_code == 422
    assert client.post("/api/planning", json={**data, "sport": "invented"}).status_code == 422
    response = client.post("/api/planning", json=data)
    assert response.status_code == 201
    value = response.json()
    changed = client.put(
        "/api/planning/" + value["id"], json={**value, "title": "Version corrigée"}
    )
    assert changed.status_code == 200 and changed.json()["revision"] == 2
    assert client.put("/api/planning/" + value["id"], json=value).status_code == 409
    calendar = client.get(f"/api/planning?start={data['day']}&end={data['day']}").json()
    assert calendar["sessions"][0]["title"] == "Version corrigée"
    assert "history" not in calendar["sessions"][0]
    assert planning.get(value["id"])["history"][0]["title"] == data["title"]
    assert client.get("/api/planning?start=2026-01-01&end=2026-12-31").status_code == 422
    assert client.put("/api/planning/unknown", json={**data, "revision": 1}).status_code == 404
    assert (
        client.put(
            "/api/planning/" + value["id"],
            json=changed.json(),
            headers={"Origin": "https://bad.example"},
        ).status_code
        == 403
    )


def test_garmin_link_requires_existing_owned_activity_and_is_unique(client, monkeypatch):
    unlock(client)
    data = body()
    p = client.post("/api/planning", json=data).json()
    url = "/api/planning/" + p["id"]
    assert client.put(url, json={**p, "status": "completed", "activity_id": "7"}).status_code == 422
    monkeypatch.setattr(db, "user_id", lambda: "other")
    db.upsert_record("activity", "7", {"duration": 600})
    monkeypatch.setattr(db, "user_id", lambda: "local")
    assert client.put(url, json={**p, "status": "completed", "activity_id": "7"}).status_code == 422
    db.upsert_record(
        "activity", "7", {"duration": 600, "startTimeLocal": data["day"] + " 09:00:00"}
    )
    linked = client.put(url, json={**p, "status": "completed", "activity_id": "7"}).json()
    second = client.post("/api/planning", json={**data, "title": "Second"}).json()
    assert (
        client.put(
            "/api/planning/" + second["id"],
            json={**second, "status": "completed", "activity_id": "7"},
        ).status_code
        == 422
    )
    assert client.put(url, json={**linked, "status": "planned"}).status_code == 422
    assert (
        client.put(url, json={**linked, "status": "planned", "activity_id": None}).status_code
        == 200
    )


def test_calendar_owner_and_gmt_to_profile_timezone(client, monkeypatch):
    unlock(client)
    db.upsert_record(
        "activity",
        "1",
        {"activityName": "Late example", "startTimeGMT": "2026-10-06 23:30:00", "duration": None},
    )
    monkeypatch.setattr(db, "user_id", lambda: "other")
    db.upsert_record("activity", "2", {"startTimeLocal": "2026-10-07 09:00:00"})
    db.upsert_record("planned_session", "private", {"day": "2026-10-07", "title": "Private"})
    monkeypatch.setattr(db, "user_id", lambda: "local")
    result = client.get("/api/planning?start=2026-10-07&end=2026-10-07").json()
    assert [a["id"] for a in result["activities"]] == ["1"]
    assert result["activities"][0]["time"] == "01:30"
    assert result["activities"][0]["duration"] is None
    assert result["sessions"] == []


def test_coach_proposes_without_marking_done_and_confirmation_survives_reload(client, monkeypatch):
    unlock(client)
    session = body()
    calls = []

    def complete(model, instructions, messages):
        calls.append(instructions)
        return json.dumps(
            {
                "answer": "Voici une proposition à confirmer.",
                "memory_proposals": [],
                "planning_proposals": [
                    {**session, "status": "completed", "activity_id": "999"},
                    {**session, "sport": "invalid"},
                ],
            }
        ), {"input_tokens": 10}

    monkeypatch.setattr(chatgpt, "complete", complete)
    response = client.post(
        "/api/chat", json={"model": "test", "content": "Propose une séance pour aujourd’hui."}
    )
    assert response.status_code == 200
    p = response.json()["planning_proposals"][0]
    assert len(response.json()["planning_proposals"]) == 1
    assert p["status"] == "proposed" and p["activity_id"] is None
    assert response.json()["usage"] == {"input_tokens": 10}
    assert len(calls) == 1 and "planning_proposals" in calls[0]
    assert client.get("/api/dashboard").json()["planning_cards"][0]["id"] == p["id"]
    assert (
        client.put("/api/planning/" + p["id"], json={**p, "status": "planned"}).status_code == 200
    )
    assert api.coach_context()["planning"]["sessions"][0]["status"] == "planned"
    assert planning.propose([session], 99) == []
    past = {
        **session,
        "day": (datetime.now(ZoneInfo("Europe/Paris")).date() - timedelta(days=1)).isoformat(),
    }
    assert planning.propose([past], 99) == []
