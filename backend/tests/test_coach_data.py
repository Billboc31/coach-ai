import json

import pytest
from fastapi.testclient import TestClient

from coach import activities, api, chatgpt, coach_data, db, memory
from coach.config import user_scope
from coach.secrets import write_secret


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    db.upsert_record(
        "activity",
        "123",
        {
            "activityName": "Séance fictive",
            "startTimeLocal": "2030-01-02 10:00:00",
            "distance": 1000,
            "duration": 600,
            "startLatitude": 99,
        },
    )
    return tmp_path


def propose():
    return coach_data.propose(
        [
            {
                "kind": "activity_details",
                "activity_id": "123",
                "fields": ["heart_rate"],
                "reason": "Observer la courbe.",
            }
        ],
        42,
        {"123"},
    )[0]


def cache(count=10):
    db.upsert_record(
        "activity_detail",
        "123",
        {
            "fetched_at": db.now(),
            "summary": {"averageHR": 120},
            "laps": [{"lapIndex": 1, "duration": 600}],
            "series": {
                "count": count,
                "status": "available",
                "axes": {"time": list(range(count)), "latitude": [99] * count},
                "channels": [
                    {"key": "heart_rate", "unit": "bpm", "values": [120] * (count - 1) + [150]},
                    {"key": "speed", "unit": "km/h", "values": [6] * count},
                ],
            },
        },
    )


def test_proposal_requires_known_activity_and_supported_fields(workspace):
    values = [
        {"kind": "arbitrary_url", "activity_id": "123"},
        {"kind": "activity_details", "activity_id": "999"},
        {"kind": "activity_details", "activity_id": "123", "fields": ["password"]},
    ]
    assert coach_data.propose(values, 42, {"123"}) == []
    request = propose()
    assert request["status"] == "proposed"
    assert coach_data.context([42]) == []  # No sharing without the click.
    with pytest.raises(LookupError):
        coach_data.context([42], request["id"])


def test_cached_read_and_targeted_context_are_bounded_and_exclude_gps(workspace, monkeypatch):
    request = propose()
    cache(4000)
    monkeypatch.setattr(activities, "refresh", lambda _: pytest.fail("must reuse cache"))
    assert coach_data.load(request["id"])["status"] == "ready"
    result = coach_data.context([42])[0]
    assert result["charts"]["source_sample_count"] == 4000
    assert len(result["charts"]["axes"]["time"]) == 180
    assert result["charts"]["axes"]["time"][-1] == 3999
    assert result["charts"]["channels"][0]["max"] == 150
    assert len(result["charts"]["channels"]) == 1
    assert "laps" not in result and "latitude" not in json.dumps(result).lower()
    assert coach_data.context([999]) == []
    assert coach_data.context([], request["id"])[0]["activity_id"] == "123"


def test_short_series_keeps_every_sample_and_missing_channel_is_explicit(workspace):
    request = propose()
    cache(10)
    coach_data.load(request["id"])
    result = coach_data.context([42])[0]
    assert result["charts"]["axes"]["time"] == list(range(10))
    assert result["charts"]["channels"][0]["values"][-1] == 150
    value = coach_data.get(request["id"])
    value["fields"] = ["power"]
    db.upsert_record("coach_data_request", request["id"], value)
    assert coach_data.context([42])[0]["charts"]["unavailable_requested_fields"] == ["power"]


def test_read_failure_does_not_claim_success(workspace, monkeypatch):
    request = propose()

    def unavailable(_):
        raise activities.DetailUnavailable("Courbes indisponibles.")

    monkeypatch.setattr(activities, "refresh", unavailable)
    with pytest.raises(activities.DetailUnavailable):
        coach_data.load(request["id"])
    assert coach_data.get(request["id"])["status"] == "proposed"
    assert coach_data.context([42]) == []


def test_owner_cannot_load_or_share_another_accounts_request(workspace):
    request = propose()
    cache()
    with user_scope("other-test-owner"):
        assert coach_data.cards() == []
        with pytest.raises(LookupError):
            coach_data.load(request["id"])
        with pytest.raises(LookupError):
            coach_data.context([], request["id"])
        assert (
            coach_data.propose([{"kind": "activity_details", "activity_id": "123"}], 42, {"123"})
            == []
        )
    assert coach_data.get(request["id"])["status"] == "proposed"


def test_reply_protocol_keeps_buttons_out_of_visible_prose():
    answer, usage = chatgpt.unpack_coach_reply(
        json.dumps(
            {
                "answer": "Je peux regarder la courbe.",
                "data_requests": [{"kind": "activity_details", "activity_id": "123"}],
            }
        ),
        {},
    )
    assert answer == "Je peux regarder la courbe."
    assert usage["_data_requests"][0]["activity_id"] == "123"
    answer, usage = chatgpt.unpack_coach_reply('Je propose de regarder.\n"data_requests":[]}', {})
    assert answer == "Je propose de regarder." and usage["_data_requests"] == []


def test_api_click_loads_then_analysis_receives_details_and_not_arbitrary_id(
    workspace, monkeypatch
):
    api.sessions.clear()
    api.login_attempts.clear()
    write_secret(workspace / "app.json", {"access_key": "test-key"})
    monkeypatch.setattr(memory, "launch", lambda *args, **kw: False)
    captured = []

    def respond(model, context, messages):
        captured.append(context)
        if context["loaded_activity_details"]:
            return "Analyse terminée avec la courbe.", {}
        return "Regardons les mesures.", {
            "_data_requests": [
                {"kind": "activity_details", "activity_id": "123", "fields": ["all"]}
            ]
        }

    monkeypatch.setattr(chatgpt, "respond", respond)
    calls = []

    def refresh(key):
        calls.append(key)
        cache()
        return activities.details(key)

    monkeypatch.setattr(activities, "refresh", refresh)
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        assert client.post("/api/coach/data/unknown/load").status_code == 401
        client.post("/api/login", json={"access_key": "test-key"})
        reply = client.post(
            "/api/chat",
            json={"model": "test", "content": "Regarde les données de ma dernière séance."},
        )
        assert reply.status_code == 200
        card = reply.json()["data_requests"][0]
        assert calls == [] and captured[0]["loaded_activity_details"] == []
        assert (
            client.post(
                "/api/coach/data/" + card["id"] + "/load",
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        api.sync_lock.acquire()
        try:
            assert client.post("/api/coach/data/" + card["id"] + "/load").status_code == 409
        finally:
            api.sync_lock.release()
        assert client.post("/api/coach/data/" + card["id"] + "/load").json()["status"] == "ready"
        assert calls == ["123"]
        result = client.post(
            "/api/chat",
            json={
                "model": "test",
                "content": "Analyse ces données.",
                "data_request_id": card["id"],
            },
        )
        assert result.status_code == 200
        assert captured[-1]["loaded_activity_details"][0]["charts"]["channels"]
        before = len(captured)
        assert (
            client.post(
                "/api/chat",
                json={"model": "test", "content": "Analyse.", "data_request_id": "forged"},
            ).status_code
            == 404
        )
        assert len(captured) == before and not api.chat_lock.locked()
        assert client.get("/api/dashboard").json()["data_cards"][0]["status"] == "ready"
