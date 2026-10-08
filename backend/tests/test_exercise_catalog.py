import json
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from coach import api, db, gym
from coach import exercise_catalog as catalogue
from coach.secrets import write_secret


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    return tmp_path


def private_exercise(key, name):
    db.upsert_record("gym_exercise", key, {"id": key, "name": name, "video_id": None})


def bind(key, catalog_id, convention="total", revision=0):
    return catalogue.set_binding(
        key,
        catalogue.BindingUpdate(
            revision=revision, catalog_id=catalog_id, weight_convention=convention
        ),
    )


def workout(key, exercise_id, *, weight=0, convention=None, catalog_id=None):
    item = {
        "id": key + "-item",
        "exercise_id": exercise_id,
        "name": "Synthetic source",
        "logged_sets": [{"weight": weight, "reps": 8, "seconds": None, "done": True}],
    }
    if convention is not None:
        item["weight_convention"] = convention
    if catalog_id is not None:
        item["catalog_id"] = catalog_id
    value = {
        "id": key,
        "program_id": "synthetic",
        "title": "Example",
        "revision": 1,
        "started_at": db.now(),
        "finished_at": db.now(),
        "exercises": [item],
    }
    db.upsert_record("gym_workout", key, value)
    return value


def test_public_catalogue_integrity_and_media_provenance():
    entries = catalogue.catalogue()
    assert len(entries) == catalogue.manifest()["count"] and len(entries) >= 800
    for key, entry in entries.items():
        assert key == "wger:" + str(entry["source_id"])
        assert entry["name"] and entry["source_url"].startswith("https://wger.de/api/")
        assert entry["credit"]["name"] in {"CC-BY-SA 3", "CC-BY-SA 4", "CC-BY 4", "CC0"}
        for media in entry["media"]:
            assert urlparse(media["url"]).hostname == "wger.de"
            assert media["credit"]["authors"]
            assert media["kind"] in {"gif", "video", "image"}
    assert any(m["kind"] == "gif" for e in entries.values() for m in e["media"])
    assert any(m["kind"] == "video" for e in entries.values() for m in e["media"])


def test_exact_names_separate_equipment_grip_and_ambiguous_names():
    assert catalogue.exact("DC barre") == "wger:73"
    assert catalogue.exact("DC haltères") == "wger:75"
    assert catalogue.exact("DC incliné haltères") == "wger:537"
    assert catalogue.exact("tractions pronation") == "wger:475"
    assert catalogue.exact("tractions supination") == "wger:152"
    assert catalogue.exact("ROWING HALTÈRE 1 BRAS") == "wger:81"
    assert catalogue.exact("leg curl assis") != catalogue.exact("leg curl allongé")
    for name in ["DC", "squat", "rowing", "gainage", "Exercice inventé 999"]:
        assert catalogue.exact(name) is None
    assert catalogue.search("DC", limit=3)["items"][0]["id"] == "wger:73"
    assert catalogue.search("DC incliné haltères", limit=3)["items"][0]["id"] == "wger:537"


def test_search_pagination_filters_and_no_alias_write(workspace):
    first = catalogue.search("", limit=6)
    second = catalogue.search("", limit=6, offset=6)
    assert len(first["items"]) == len(second["items"]) == 6
    assert {e["id"] for e in first["items"]}.isdisjoint(e["id"] for e in second["items"])
    filtered = catalogue.search("", equipment="Dumbbell", category="Chest")
    assert all("Dumbbell" in e["equipment"] and e["category"] == "Chest" for e in filtered["items"])
    assert db.records("gym_binding") == []


def test_binding_revision_clear_and_owner_scope(workspace, monkeypatch):
    private_exercise("alias", "DC")
    assert catalogue.resolution("alias")["entry"] is None
    bound = bind("alias", "wger:73")
    assert bound["entry"]["name"] == "Développé couché à la barre"
    assert catalogue.resolution("alias")["revision"] == 1
    with pytest.raises(catalogue.BindingConflict):
        bind("alias", "wger:75")
    with pytest.raises(ValueError):
        bind("alias", "not-in-catalogue", revision=1)
    assert bind("alias", None, revision=1)["entry"] is None
    monkeypatch.setattr(db, "user_id", lambda: "other")
    monkeypatch.setattr(catalogue, "user_id", lambda: "other")
    assert catalogue.resolution("alias")["entry"] is None
    assert bind("alias", "wger:73", revision=2) is None


def test_synonyms_pool_only_confirmed_compatible_weights_without_mutation(workspace):
    private_exercise("first", "DC")
    private_exercise("second", "Bench press")
    private_exercise("different", "DC haltères")
    first = workout("one", "first", weight=0)
    second = workout("two", "second", weight=30)
    third = workout("three", "different", weight=10)
    bind("first", "wger:73", "total")
    bind("second", "wger:73", "per_dumbbell")
    bind("different", "wger:75", "total")
    assert catalogue.compatible_ids("first") == ["first"]
    assert [h["workout_id"] for h in gym.history("first")] == ["one"]
    bind("second", "wger:73", "total", revision=1)
    assert catalogue.compatible_ids("first") == ["first", "second"]
    assert {h["workout_id"] for h in gym.history("first")} == {"one", "two"}
    assert any(h["sets"][0]["weight"] == 0 for h in gym.history("first"))
    for saved in (first, second, third):
        assert db.record("gym_workout", saved["id"]) == saved
    bind("second", "wger:75", "total", revision=2)
    assert [h["workout_id"] for h in gym.history("first")] == ["one"]


def test_unknown_conventions_and_recorded_different_variants_never_pool(workspace):
    private_exercise("first", "DC barre")
    private_exercise("second", "Barbell bench press")
    workout("unknown", "first")
    workout("other-unknown", "second")
    bind("first", "wger:73", "unspecified")
    bind("second", "wger:73", "unspecified")
    assert catalogue.compatible_ids("first") == ["first"]
    bind("first", "wger:73", "total", revision=1)
    bind("second", "wger:73", "total", revision=1)
    workout("recorded-as-per-dumbbell", "second", convention="per_dumbbell", catalog_id="wger:73")
    workout("recorded-as-different-variant", "second", convention="total", catalog_id="wger:75")
    assert {h["workout_id"] for h in gym.history("first")} == {"unknown", "other-unknown"}


def test_imported_history_pools_compatible_aliases_and_keeps_raw_weights(workspace):
    for key in ("a", "b"):
        private_exercise(key, "Synthetic")
        db.upsert_record(
            "gym_excel_history",
            key,
            {
                "id": key,
                "exercise_id": key,
                "performance": ["5", "X"],
                "row": 1,
                "imported_at": db.now(),
            },
        )
        bind(key, "wger:75", "per_dumbbell")
    rows = gym.imported_history("a")
    assert len(rows) == 2
    assert all(r["weights_kg"] == [5, 5] and r["performance_sets"][0]["reps"] is None for r in rows)
    assert "weights_kg" not in db.record("gym_excel_history", "a")


def test_catalogue_api_auth_csrf_limits_and_confirm(workspace):
    private_exercise("alias", "DC")
    write_secret(workspace / "app.json", {"access_key": "test-key"})
    api.sessions.clear()
    api.login_attempts.clear()
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as client:
        assert client.get("/api/gym/catalogue?q=DC").status_code == 401
        client.post("/api/login", json={"access_key": "test-key"})
        assert client.get("/api/gym/catalogue?limit=100").status_code == 422
        assert client.get("/api/gym/catalogue?offset=-1").status_code == 422
        assert client.get("/api/gym/catalogue?q=" + "a" * 201).status_code == 422
        result = client.get("/api/gym/catalogue?q=DC&limit=3").json()
        assert len(result["items"]) == 3 and result["catalogue"]["count"] >= 800
        assert client.get("/api/gym/exercises/alias/catalogue").json()["method"] == "unresolved"
        path = "/api/gym/exercises/alias/catalogue"
        payload = {"revision": 0, "catalog_id": "wger:73", "weight_convention": "total"}
        assert (
            client.put(path, json=payload, headers={"Origin": "https://bad.example"}).status_code
            == 403
        )
        assert client.put(path, json=payload).json()["entry"]["id"] == "wger:73"
        assert client.put(path, json=payload).status_code == 409
        assert client.get("/api/gym/exercises/unknown/catalogue").status_code == 404
        assert client.put("/api/gym/exercises/unknown/catalogue", json=payload).status_code == 404
        assert client.get("/api/gym/exercises/alias/history").json()["sessions"] == []
        assert (
            json.dumps(client.get("/api/gym/exercises/alias/catalogue").json()).find("wger:73") >= 0
        )


def test_machine_aliases_require_the_same_explicit_machine_context(workspace):
    for key in ("a", "b"):
        private_exercise(key, "Synthetic machine")
        bind(key, "wger:371", "machine")
    assert catalogue.compatible_ids("a") == ["a"]
    for key, context in [("a", "machine A"), ("b", "machine B")]:
        catalogue.set_binding(
            key,
            catalogue.BindingUpdate(
                revision=1,
                catalog_id="wger:371",
                weight_convention="machine",
                weight_context=context,
            ),
        )
    assert catalogue.compatible_ids("a") == ["a"]
    catalogue.set_binding(
        "b",
        catalogue.BindingUpdate(
            revision=2,
            catalog_id="wger:371",
            weight_convention="machine",
            weight_context="machine A",
        ),
    )
    assert catalogue.compatible_ids("a") == ["a", "b"]


def test_automatic_equivalent_wording_keeps_all_variant_constraints():
    cases = {
        "Haltères développé couché incliné": "wger:537",
        "DC avec haltère": "wger:75",
        "Rowing unilatéral avec haltère": "wger:81",
        "Curl avec barre EZ": "wger:94",
        "Barre rowing supi": "wger:84",
        "SDT roumain avec barre": "wger:507",
    }
    for name, expected in cases.items():
        assert catalogue.automatic(name) == (expected, "automatic")
    for name in [
        "DC",
        "Squat",
        "Curl biceps",
        "Gainage",
        "Rowing",
        "DC avec haltères sans banc",
        "Rowing haltère deux bras",
        "DC barre incliné supination",
        "SDT roumain avec machine",
        "Curl barre EZ inversé",
        "Invented exercise 999",
    ]:
        assert catalogue.automatic(name) == (None, "unresolved")


def test_automatic_resolution_respects_manual_choices_and_does_not_classify_weights(workspace):
    private_exercise("alias", "Rowing unilatéral avec haltère")
    saved = workout("old", "alias", weight=15)
    result = catalogue.resolution("alias")
    assert result["method"] == "automatic" and result["catalog_id"] == "wger:81"
    assert result["weight_convention"] == "unspecified"
    assert db.records("gym_binding") == []
    assert catalogue.compatible_ids("alias") == ["alias"]
    bind("alias", "wger:75")
    assert catalogue.resolution("alias")["catalog_id"] == "wger:75"
    bind("alias", None, revision=1)
    assert catalogue.resolution("alias")["catalog_id"] is None
    assert (
        catalogue.decorate(
            {"exercise_id": "alias", "name": "Rowing unilatéral haltère"}, catalogue.decisions()
        )["catalog_id"]
        is None
    )
    assert db.record("gym_workout", "old") == saved


def test_existing_programs_are_automatically_resolved_across_all_days(workspace):
    exercises = [
        {"id": "first", "exercise_id": "alias", "name": "Rowing unilatéral haltère"},
        {"id": "second", "exercise_id": "incline", "name": "Haltères développé couché incliné"},
        {"id": "third", "exercise_id": "unknown", "name": "DC"},
    ]
    for item in exercises:
        private_exercise(item["exercise_id"], item["name"])
    program = {
        "id": "program",
        "title": "Synthetic",
        "display_version": 2,
        "days": [{"id": str(i), "exercises": [item]} for i, item in enumerate(exercises)],
    }
    db.upsert_record("gym_program", "program", program)
    actual = gym.overview()["programs"][0]
    assert [d["exercises"][0]["catalog_id"] for d in actual["days"]] == [
        "wger:81",
        "wger:537",
        None,
    ]
    assert db.record("gym_program", "program") == program
    assert db.records("gym_binding") == []


def test_documented_primary_and_secondary_muscles_are_kept_separate():
    bench = catalogue.catalogue()["wger:73"]
    assert bench["muscles"] == ["Chest"]
    assert set(bench["muscles_secondary"]) == {"Shoulders", "Triceps"}
    assert catalogue.catalogue()["wger:81"]["muscles_secondary"] == []


def test_coaching_vocabulary_preserves_machine_bar_and_rope_variants():
    examples = {
        "DVP épaule avec barre": "wger:566",
        "DVP épaules haltères assis": "wger:567",
        "Développé épaule cadre guidé": "wger:569",
        "Curl Larry Scott barre EZ": "wger:465",
        "Ischio leg curl machine assis": "wger:366",
        "Leg curl machine allongé": "wger:365",
        "Triceps poulie barre": "wger:660",
        "Triceps poulie corde": "wger:805",
        "Gamme montante DVP épaules haltères assis tension continue": "wger:567",
    }
    for name, expected in examples.items():
        assert catalogue.automatic(name)[0] == expected
    for name in [
        "DVP couché",
        "Triceps poulie",
        "Abdos conf fiche",
        "Fiche mobilité",
        "DVP épaule haltère debout",
        "DVP épaule cadre guidé un bras",
    ]:
        assert catalogue.automatic(name)[0] is None
