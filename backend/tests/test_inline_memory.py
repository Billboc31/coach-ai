import json

import pytest
from fastapi.testclient import TestClient

from coach import api, chatgpt, db, memory
from coach.secrets import write_secret


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    api.sessions.clear()
    api.login_attempts.clear()
    write_secret(tmp_path / "app.json", {"access_key": "test-key"})
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as c:
        c.post("/api/login", json={"access_key": "test-key"})
        yield c


def test_first_exchange_proposes_sourced_memory_without_extra_inference(client, monkeypatch):
    calls = []
    question = "Je préfère courir le matin."

    def complete(model, instructions, messages):
        calls.append(messages)
        return json.dumps(
            {
                "answer": "D’accord, nous en tiendrons compte.",
                "memory_proposals": [
                    {
                        "content": "Préfère courir le matin.",
                        "category": "preference",
                        "quote": question,
                        "expires_on": None,
                    }
                ],
            }
        ), {"input_tokens": 10}

    monkeypatch.setattr(chatgpt, "complete", complete)
    response = client.post("/api/chat", json={"content": question, "model": "test"})
    assert response.status_code == 200
    assert response.json()["content"] == "D’accord, nous en tiendrons compte."
    assert response.json()["usage"] == {"input_tokens": 10}
    assert len(calls) == 1
    fact = response.json()["memory_proposals"][0]
    transcript = db.history("messages")
    assert fact["source_ids"] == [transcript[0]["id"]]
    assert fact["chat_message_id"] == transcript[1]["id"]
    assert fact["status"] == "proposed"
    assert memory.context("", [])["confirmed_facts"] == []
    # Inline cards survive page reload and can be confirmed through the existing private API.
    assert client.get("/api/dashboard").json()["memory_cards"][0]["id"] == fact["id"]
    assert (
        client.put("/api/memory/facts/" + fact["id"], json={**fact, "status": "active"}).status_code
        == 200
    )
    assert client.get("/api/dashboard").json()["memory_cards"][0]["status"] == "active"
    assert memory.context("", [])["confirmed_facts"][0]["content"] == fact["content"]


def test_unsupported_proposals_do_not_discard_valid_reply(client, monkeypatch):
    monkeypatch.setattr(
        chatgpt,
        "complete",
        lambda *args: (
            json.dumps(
                {
                    "answer": "Réponse valide.",
                    "memory_proposals": [
                        {
                            "content": "Information inventée",
                            "category": "preference",
                            "quote": "Texte absent",
                        }
                    ],
                }
            ),
            {},
        ),
    )
    response = client.post("/api/chat", json={"content": "Bonjour", "model": "test"})
    assert response.status_code == 200
    assert response.json()["memory_proposals"] == []
    assert memory.state()["facts"] == []
    assert len(db.history("messages")) == 2


def test_ignored_inline_proposal_not_reintroduced_by_summary(client, monkeypatch):
    source = {
        "id": db.append("messages", "Je préfère courir le matin.", "user"),
        "role": "user",
        "content": "Je préfère courir le matin.",
        "created_at": db.now(),
    }
    assistant_id = db.append("messages", "D’accord.", "assistant")
    facts = memory.propose_from_reply(
        [{"content": "Préfère le matin.", "category": "preference", "quote": source["content"]}],
        source,
        assistant_id,
    )
    fact = facts[0]
    memory.edit_fact(fact["id"], fact["content"], fact["category"], None, "rejected")

    # Source of rejected proposal is excluded from derived summaries.
    def complete(model, instructions, messages):
        value = json.loads(messages[0]["content"])
        assert all(m["id"] != source["id"] for m in value["messages"])
        return '{"summary":"Le coach a répondu.","facts":[]}', {}

    monkeypatch.setattr(chatgpt, "complete", complete)
    memory.update("test")
    assert len(memory.state()["facts"]) == 1
    assert memory.state()["facts"][0]["status"] == "rejected"


def test_same_source_not_duplicated_by_background_summary(client, monkeypatch):
    row_id = db.append("messages", "Je préfère courir le matin.", "user")
    source = db.history("messages", 1)[0]
    assistant_id = db.append("messages", "D’accord.", "assistant")
    memory.propose_from_reply(
        [{"content": "Préfère le matin.", "category": "preference", "quote": source["content"]}],
        source,
        assistant_id,
    )
    monkeypatch.setattr(
        chatgpt,
        "complete",
        lambda *args: (
            json.dumps(
                {
                    "summary": "Préférence datée.",
                    "facts": [
                        {
                            "content": "Autre formulation du même souvenir",
                            "category": "preference",
                            "quote": source["content"],
                            "source_id": row_id,
                            "expires_on": None,
                        }
                    ],
                }
            ),
            {},
        ),
    )
    memory.update("test")
    assert len(memory.state()["facts"]) == 1


@pytest.mark.parametrize("text", ['{"answer":', '{"memory_proposals": []}', '["answer"]'])
def test_invalid_wrapped_reply_not_saved_as_coaching(client, monkeypatch, text):
    monkeypatch.setattr(chatgpt, "complete", lambda *args: (text, {}))
    response = client.post("/api/chat", json={"content": "Bonjour", "model": "test"})
    assert response.status_code == 503
    assert db.history("messages") == []


def test_plain_completed_reply_remains_compatible():
    assert chatgpt.unpack_coach_reply("Une réponse normale.", {"input_tokens": 1}) == (
        "Une réponse normale.",
        {"input_tokens": 1},
    )
    assert (
        chatgpt.unpack_coach_reply('```json\n{"answer":"OK","memory_proposals":[]}\n```', {})[0]
        == "OK"
    )


@pytest.mark.parametrize(
    "raw",
    [
        'Réponse naturelle.","memory_proposals":[],"planning_proposals":[]}',
        'Réponse naturelle.,"planning_proposals":[],"memory_proposals":[]}',
        'Réponse naturelle.\n"memory_proposals": [], "planning_proposals": []',
        '```json\nRéponse naturelle.","memory_proposals":[],"planning_proposals":[]}\n```',
    ],
)
def test_mixed_prose_reply_hides_protocol_metadata(raw):
    answer, usage = chatgpt.unpack_coach_reply(raw, {"input_tokens": 12})
    assert answer == "Réponse naturelle."
    assert usage == {"input_tokens": 12, "_memory_proposals": [], "_planning_proposals": []}


def test_mixed_prose_keeps_sourced_cards_separate_and_only_stores_answer(client, monkeypatch):
    question = "Je préfère m’entraîner tôt."
    proposals = [
        {"content": "Préfère s’entraîner tôt.", "category": "preference", "quote": question}
    ]
    tail = json.dumps({"memory_proposals": proposals, "planning_proposals": []}, ensure_ascii=False)
    raw = 'D’accord pour les séances tôt.",' + tail[1:]
    monkeypatch.setattr(chatgpt, "complete", lambda *args: (raw, {"input_tokens": 4}))
    response = client.post("/api/chat", json={"content": question, "model": "test"})
    assert response.status_code == 200
    assert response.json()["content"] == "D’accord pour les séances tôt."
    assert response.json()["memory_proposals"][0]["status"] == "proposed"
    assert len(db.history("messages")) == 2
    assert db.history("messages")[-1]["content"] == "D’accord pour les séances tôt."
    assert memory.context("", [])["confirmed_facts"] == []


def test_historical_metadata_is_hidden_without_rewriting_source_or_user_text(client, monkeypatch):
    raw = 'Ancienne réponse.","memory_proposals":[],"planning_proposals":[]}'
    user_id = db.append("messages", raw, "user")
    assistant_id = db.append("messages", raw, "assistant")
    original = db.history("messages")
    rows = client.get("/api/dashboard").json()["messages"]
    assert rows[0]["id"] == user_id and rows[0]["content"] == raw
    assert rows[1]["id"] == assistant_id and rows[1]["content"] == "Ancienne réponse."
    captured = []
    monkeypatch.setattr(
        chatgpt,
        "complete",
        lambda model, instructions, messages: (
            captured.append(messages) or '{"answer":"OK","memory_proposals":[]}',
            {},
        ),
    )
    chatgpt.respond(
        "test",
        {"request_memory_proposals": True},
        original + [{"role": "user", "content": "Suite"}],
    )
    assert captured[0][-2]["content"] == "Ancienne réponse."
    assert captured[0][-3]["content"] == raw
    assert db.history("messages") == original


def test_ordinary_mentions_are_not_stripped_and_invalid_metadata_is_not_saved(client, monkeypatch):
    ordinary = "Le nom memory_proposals est un champ technique, pas un souvenir."
    assert chatgpt.unpack_coach_reply(ordinary, {}) == (ordinary, {})
    raw = 'Réponse.","memory_proposals":[{"content":'
    monkeypatch.setattr(chatgpt, "complete", lambda *args: (raw, {}))
    assert client.post("/api/chat", json={"content": "Bonjour", "model": "test"}).status_code == 503
    assert db.history("messages") == []
