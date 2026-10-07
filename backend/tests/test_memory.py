import json
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from coach import api, db, memory
from coach.secrets import write_secret


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(memory, "today", lambda: date(2026, 10, 7))
    return tmp_path


def message(content="Je préfère courir le matin.", role="user"):
    db.append("messages", content, role)
    return db.history("messages", 1)[0]


def result(row, summary="Préférence exprimée dans la discussion."):
    return json.dumps(
        {
            "summary": summary,
            "facts": [
                {
                    "content": "Préfère courir le matin.",
                    "category": "preference",
                    "source_id": row["id"],
                    "quote": row["content"],
                    "expires_on": None,
                }
            ],
        }
    )


def test_migration_indexes_existing_history_and_preserves_profile(local):
    with sqlite3.connect(local / "coach.db") as conn:
        for sql in db.SCHEMA:
            conn.execute(sql)
        conn.execute("INSERT INTO schema_version VALUES (1)")
        conn.execute("INSERT INTO profiles VALUES (?,?)", ("local", '{"name":"Athlete"}'))
        conn.execute(
            "INSERT INTO messages(user_id,role,content,created_at) VALUES (?,?,?,?)",
            ("local", "user", "Ancienne récupération", "2020-01-01"),
        )
    assert db.profile()["name"] == "Athlete"
    assert db.search_messages('"recuperation"', set())[0]["content"] == "Ancienne récupération"
    # Reopening the DB must not duplicate the search index.
    assert len(db.search_messages('"recuperation"', set())) == 1
    with db.connection() as conn:
        versions = [r[0] for r in conn.execute(db.text("SELECT version FROM schema_version"))]
    assert versions == [1, 2]


def test_search_finds_old_accented_messages_and_is_owner_scoped(local, monkeypatch):
    old = message("La récupération après le tennis est difficile.")
    for i in range(25):
        message(f"Échange neutre {i}")
    context = memory.context("Parlons de ma recuperation", [])
    assert context["relevant_past_messages"][0]["id"] == old["id"]
    assert memory.context('" OR récupération ?', [old["id"]])["relevant_past_messages"] == []
    monkeypatch.setattr(db, "user_id", lambda: "another")
    assert memory.context("recuperation", [])["relevant_past_messages"] == []
    assert memory.view()["facts"] == []


def test_summary_and_proposals_persist_with_sources_and_checkpoint(local, monkeypatch):
    row = message()
    monkeypatch.setattr(
        memory.chatgpt, "complete", lambda *args: (result(row), {"input_tokens": 5})
    )
    memory.update("test-model")
    saved = memory.view()
    assert saved["through_id"] == row["id"]
    assert saved["summary"]
    fact = saved["facts"][0]
    assert fact["status"] == "proposed"
    assert fact["source_ids"] == [row["id"]]
    assert memory.context("", [])["confirmed_facts"] == []
    memory.edit_fact(fact["id"], fact["content"], fact["category"], None, "active")
    assert memory.context("", [])["confirmed_facts"][0]["content"] == fact["content"]
    # No new message means no extra inference or duplicated memory.
    monkeypatch.setattr(
        memory.chatgpt, "complete", lambda *args: pytest.fail("Unexpected inference")
    )
    memory.update("test-model")
    assert len(memory.view()["facts"]) == 1


@pytest.mark.parametrize("fault", ["assistant", "quote", "expiry", "json", "incomplete"])
def test_bad_derived_memory_does_not_replace_saved_state(local, monkeypatch, fault):
    row = message(role="assistant" if fault == "assistant" else "user")
    value = json.loads(result(row))
    if fault == "quote":
        value["facts"][0]["quote"] = "invented"
    if fault == "expiry":
        value["facts"][0]["expires_on"] = "2026-12-01"
    original = memory.state()
    original["summary"] = "Résumé précédent"
    memory.save(original)
    before = memory.state()

    def complete(*args):
        if fault == "incomplete":
            raise ValueError("stream incomplete")
        return ("invalid JSON" if fault == "json" else json.dumps(value), {})

    monkeypatch.setattr(memory.chatgpt, "complete", complete)
    with pytest.raises(ValueError):
        memory.update("test")
    assert memory.state() == before


def test_manual_correction_wins_over_in_flight_summary(local, monkeypatch):
    row = message()
    fact = memory.edit_fact(None, "Préfère le soir.", "preference", None, "active")

    def complete(*args):
        memory.edit_fact(fact["id"], "Préfère le midi.", "preference", None, "active")
        return result(row), {}

    monkeypatch.setattr(memory.chatgpt, "complete", complete)
    with pytest.raises(ValueError):
        memory.update("test")
    assert memory.state()["facts"][0]["content"] == "Préfère le midi."
    assert memory.state()["through_id"] == 0


def test_correction_or_deletion_invalidates_stale_summary_and_source(local, monkeypatch):
    row = message()
    monkeypatch.setattr(memory.chatgpt, "complete", lambda *args: (result(row), {}))
    memory.update("test")
    fact = memory.state()["facts"][0]
    memory.edit_fact(fact["id"], "Préfère courir le soir.", "preference", None, "active")
    assert memory.state()["summary"] == ""
    assert row["id"] in memory.state()["suppressed_ids"]
    assert memory.context("matin", [])["relevant_past_messages"] == []
    memory.remove_fact(fact["id"])
    assert memory.state()["facts"] == []
    assert db.history("messages")[0]["content"] == row["content"]


def test_expired_and_archived_goals_do_not_become_current_context(local):
    memory.edit_fact(None, "Objectif passé", "goal", "2025-01-01", "active")
    memory.edit_fact(None, "Objectif archivé", "goal", None, "archived")
    active = memory.edit_fact(None, "Objectif actuel", "goal", "2027-01-01", "active")
    assert [f["id"] for f in memory.context("", [])["confirmed_facts"]] == [active["id"]]


def test_batch_checkpoint_and_retry_do_not_drop_older_messages(local, monkeypatch):
    for i in range(35):
        message(f"Texte neutre {i}")
    seen = []

    def complete(model, instructions, messages):
        data = json.loads(messages[0]["content"])
        seen.append([m["id"] for m in data["messages"]])
        return '{"summary":"Résumé daté.","facts":[]}', {}

    monkeypatch.setattr(memory.chatgpt, "complete", complete)
    memory.update("test")
    assert memory.state()["through_id"] == 30
    memory.update("test")
    assert memory.state()["through_id"] == 35
    assert seen == [list(range(1, 31)), list(range(31, 36))]


def test_auto_update_threshold_failure_and_disable(local, monkeypatch):
    for i in range(9):
        message(f"Texte neutre {i}")
    assert not memory.launch("test")
    message("Dixième message")

    class Inline:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(memory.threading, "Thread", Inline)
    monkeypatch.setattr(memory.chatgpt, "complete", lambda *args: ("broken", {}))
    assert memory.launch("test")
    assert memory.view()["job"]["status"] == "failed"
    assert not memory.generation_lock.locked()
    assert memory.state()["through_id"] == 0
    memory.settings(False)
    assert not memory.launch("test")
    db.upsert_record("memory", "job", {"status": "running"})
    memory.recover()
    assert memory.view()["job"]["status"] == "interrupted"


def test_twenty_recent_activities_and_targeted_month_totals(local):
    # IDs deliberately ordered opposite to dates: selection must use activity time.
    for day in range(1, 32):
        db.upsert_record(
            "activity",
            str(100 - day),
            {
                "startTimeLocal": f"2025-05-{day:02d} 10:00:00",
                "duration": 60,
                "activityType": {"typeKey": "running"},
                "startLatitude": 40,
            },
        )
    db.upsert_record(
        "activity",
        "0",
        {"startTimeLocal": "2026-10-06 10:00:00", "activityType": {"typeKey": "tennis"}},
    )
    context = api.coach_context("Analyse ma course de mai 2025")
    assert len(context["recent_activities"]) == 20
    assert context["recent_activities"][0]["startTimeLocal"].startswith("2026-10-06")
    selected = context["selected_activity_period"]
    assert selected["totals"]["count"] == 31
    assert selected["totals"]["duration_seconds"] == 1860
    assert selected["totals"]["distance_meters"] is None
    assert len(selected["items"]) == 30
    assert "startLatitude" not in json.dumps(context)
    assert memory.activity_selection("du 2025-05-02 au 2025-05-03")["totals"]["count"] == 2
    assert memory.activity_selection("2025-13-40") is None
    assert memory.activity_selection("la semaine dernière")["start"] == "2026-09-28"


def test_memory_api_is_private_editable_and_used_in_chat(local, monkeypatch):
    write_secret(local / "app.json", {"access_key": "test-key"})
    api.sessions.clear()
    api.login_attempts.clear()
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        assert client.get("/api/memory").status_code == 401
        client.post("/api/login", json={"access_key": "test-key"})
        assert (
            client.post(
                "/api/memory/facts",
                json={"content": "Test"},
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        assert client.post("/api/memory/facts", json={"content": " "}).status_code == 422
        fact = client.post("/api/memory/facts", json={"content": "Jour de repos lundi"}).json()
        assert (
            client.put(
                "/api/memory/facts/" + fact["id"], json={"content": "Jour de repos mardi"}
            ).status_code
            == 200
        )

        def respond(model, context, messages):
            assert context["memory"]["confirmed_facts"][0]["content"] == "Jour de repos mardi"
            return "Réponse terminée.", {}

        monkeypatch.setattr(api.chatgpt, "respond", respond)
        monkeypatch.setattr(
            memory, "launch", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError())
        )
        assert (
            client.post("/api/chat", json={"content": "Mon repos ?", "model": "test"}).status_code
            == 200
        )
        assert len(db.history("messages")) == 2
        assert client.delete("/api/memory/facts/" + fact["id"]).status_code == 200
        assert client.get("/api/memory").json()["facts"] == []
