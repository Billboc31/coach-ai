import json

import pytest
from fastapi.testclient import TestClient

from coach import api, chatgpt, db, memory
from coach.secrets import write_secret


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    return tmp_path


def existing(content="Contrainte temporaire en cours.", category="constraint"):
    return memory.edit_fact(None, content, category, None, "active")


def suggestion(target, action="archive", content="La contrainte est terminée."):
    source_id = db.append("messages", content, "user")
    source = db.history("messages", 1)[0]
    assistant_id = db.append("messages", "Je peux mettre à jour ce souvenir.", "assistant")
    proposals = [
        {
            "action": action,
            "target_id": target["id"],
            "target_version": memory.fingerprint(target),
            "content": content,
            "category": target["category"],
            "quote": source["content"],
        }
    ]
    return memory.propose_from_reply(proposals, source, assistant_id), source_id


def confirm(fact):
    return memory.edit_fact(fact["id"], fact["content"], fact["category"], None, "active")


def test_resolution_is_proposed_then_archives_original_with_dated_history(local):
    target = existing("Gêne au poignet signalée.", "health_context")
    cards, source_id = suggestion(target, content="Je ne ressens plus de gêne au poignet.")
    assert len(cards) == 1
    assert cards[0]["target_content"] == target["content"]
    assert memory.state()["facts"][0]["status"] == "active"
    result = confirm(cards[0])
    assert result["status"] == "applied"
    old, event = memory.state()["facts"]
    assert old["status"] == "archived"
    assert old["ended_at"] == event["source_date"]
    assert old["replaced_by"] == event["id"]
    assert old["content"] == "Gêne au poignet signalée."
    context = memory.context("", [])
    assert context["confirmed_facts"] == []
    assert context["recent_memory_changes"][0]["action"] == "archive"
    assert len(db.history("messages")) == 2
    assert source_id == event["source_ids"][0]
    # Repeated clicks are idempotent and do not resurrect the original condition.
    confirm(event)
    assert memory.state()["facts"][0]["status"] == "archived"
    assert len(memory.state()["facts"]) == 2


def test_replacement_preserves_old_goal_but_only_new_goal_is_current(local):
    target = existing("Objectif : épreuve A.", "goal")
    cards, _ = suggestion(target, action="replace", content="Mon objectif devient l’épreuve B.")
    confirm(cards[0])
    old, new = memory.state()["facts"]
    assert old["status"] == "archived"
    assert new["status"] == "active"
    assert new["target_id"] == old["id"]
    assert [f["content"] for f in memory.context("", [])["confirmed_facts"]] == [new["content"]]
    # The replacement can itself later be resolved.
    closures, _ = suggestion(new)
    confirm(closures[0])
    assert memory.context("", [])["confirmed_facts"] == []


def test_ignoring_change_preserves_original_state(local):
    target = existing()
    cards, _ = suggestion(target)
    memory.edit_fact(cards[0]["id"], cards[0]["content"], cards[0]["category"], None, "rejected")
    assert memory.state()["facts"][0]["status"] == "active"
    assert [f["id"] for f in memory.context("", [])["confirmed_facts"]] == [target["id"]]


@pytest.mark.parametrize("change", ["edit", "delete", "archive"])
def test_stale_confirmation_does_not_overwrite_changes(local, change):
    target = existing()
    cards, _ = suggestion(target)
    if change == "edit":
        memory.edit_fact(
            target["id"], "Nouvelle contrainte corrigée.", target["category"], None, "active"
        )
    elif change == "delete":
        memory.remove_fact(target["id"])
    else:
        memory.edit_fact(target["id"], target["content"], target["category"], None, "archived")
    before = memory.state()
    with pytest.raises(memory.ConflictError):
        confirm(cards[0])
    assert memory.state() == before


def test_unknown_foreign_or_changed_target_is_never_proposed(local, monkeypatch):
    target = existing()
    monkeypatch.setattr(db, "user_id", lambda: "other-user")
    cards, _ = suggestion(target)
    assert cards == []
    monkeypatch.setattr(db, "user_id", lambda: "local")
    memory.edit_fact(target["id"], "Information corrigée.", target["category"], None, "active")
    cards, _ = suggestion(target)  # Old version seen by inference.
    assert cards == []


def test_background_extraction_can_propose_a_sourced_change(local, monkeypatch):
    target = existing()
    source_id = db.append("messages", "La contrainte est terminée.", "user")
    monkeypatch.setattr(
        chatgpt,
        "complete",
        lambda *args: (
            json.dumps(
                {
                    "summary": "Fin déclarée.",
                    "facts": [
                        {
                            "action": "archive",
                            "target_id": target["id"],
                            "target_version": memory.fingerprint(target),
                            "source_id": source_id,
                            "content": "La contrainte est terminée.",
                            "quote": "La contrainte est terminée.",
                            "category": "constraint",
                            "expires_on": None,
                        }
                    ],
                }
            ),
            {},
        ),
    )
    memory.update("test")
    assert memory.state()["facts"][0]["status"] == "active"
    assert memory.state()["facts"][1]["action"] == "archive"


def test_chat_round_trip_and_conflict_return_safe_status(local, monkeypatch):
    write_secret(local / "app.json", {"access_key": "test-key"})
    api.sessions.clear()
    api.login_attempts.clear()
    target = existing()

    def complete(model, instructions, messages):
        assert "action=archive" in instructions
        return json.dumps(
            {
                "answer": "Je te propose de clôturer ce souvenir.",
                "memory_proposals": [
                    {
                        "action": "archive",
                        "target_id": target["id"],
                        "target_version": memory.fingerprint(target),
                        "content": "Contrainte terminée.",
                        "category": "constraint",
                        "quote": "La contrainte est terminée.",
                        "expires_on": None,
                    }
                ],
            }
        ), {}

    monkeypatch.setattr(chatgpt, "complete", complete)
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        client.post("/api/login", json={"access_key": "test-key"})
        response = client.post(
            "/api/chat", json={"content": "La contrainte est terminée.", "model": "test"}
        )
        assert response.status_code == 200
        card = response.json()["memory_proposals"][0]
        assert card["target_id"] == target["id"]
        memory.edit_fact(
            target["id"], "Souvenir corrigé entre-temps.", target["category"], None, "active"
        )
        response = client.put("/api/memory/facts/" + card["id"], json={**card, "status": "active"})
        assert response.status_code == 409
        assert memory.state()["facts"][0]["content"] == "Souvenir corrigé entre-temps."
