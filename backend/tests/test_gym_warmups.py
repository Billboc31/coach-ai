"""Synthetic session-local ramp warm-ups; never use a private training workbook."""

import base64
import copy
import io

import pytest
from openpyxl import Workbook

from coach import db, exercise_catalog, gym, gym_warmups
from coach.config import user_scope


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    catalogue = {
        "repdb:synthetic-shoulder": {"name": "Développé épaules", "media": []},
        "repdb:synthetic-incline": {"name": "Développé couché incliné", "media": []},
    }
    monkeypatch.setattr(exercise_catalog, "catalogue", lambda: catalogue)
    monkeypatch.setattr(
        exercise_catalog,
        "automatic",
        lambda name: (
            ("repdb:synthetic-incline" if "incliné" in name else "repdb:synthetic-shoulder"),
            "automatic",
        ),
    )


def item(key, name):
    return {
        "id": key,
        "exercise_id": key,
        "name": name,
        "sets": 3,
        "reps": "10",
        "weight": None,
        "performance": [],
    }


def imported():
    book = Workbook()
    sheet = book.active
    sheet.title = "Cycle synthétique"
    for row in [
        ["Ordre", "Exercices", "Séries", "Répétitions", "Performance"],
        ["", "Séance 1"],
        ["a", "Gamme montante développé épaules", 1, "12\n8\n5", 10],
        ["A", "Développé épaules", 3, "8", 50],
        ["", "Séance 2"],
        ["a", "Gamme montante développé épaules", 1, "12\n8\n5", 15],
        ["A", "Développé couché incliné", 3, "8", 60],
    ]:
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    preview = gym.preview("synthetic.xlsx", base64.b64encode(stream.getvalue()).decode())
    selection = gym.ImportSelection(
        title="Synthetic",
        performances_are_kg=True,
        sheets=[
            gym.SheetMapping(
                name=sheet.title,
                header=0,
                mapping={"order": 0, "name": 1, "sets": 2, "reps": 3, "performance": 4},
            )
        ],
    )
    return gym.confirm(preview["id"], selection)


def test_any_movement_is_resolved_within_its_own_session(workspace):
    for target in ["Squat", "Rowing", "Soulevé de terre", "Développé couché incliné"]:
        source = [item("ramp", "Gamme montante"), item("work", target)]
        before = copy.deepcopy(source)
        resolved = gym_warmups.resolve(source)
        assert source == before
        assert resolved[0]["name"] == "Gamme montante " + target
        assert resolved[0]["source_name"] == "Gamme montante"
        assert resolved[0]["warmup_for_id"] == "work"
        assert resolved[0]["exercise_id"] != resolved[1]["exercise_id"]
        assert resolved[0]["weight"] is None
        assert gym_warmups.resolve(resolved) == resolved


def test_import_corrects_repeated_wrong_label_and_keeps_source_and_weights(workspace):
    program = imported()
    first, second = [d["exercises"] for d in program["days"]]
    assert first[0]["name"] == "Gamme montante Développé épaules"
    assert second[0]["name"] == "Gamme montante Développé couché incliné"
    assert first[0]["exercise_id"] != second[0]["exercise_id"]
    assert second[0]["source_name"] == "Gamme montante développé épaules"
    assert second[0]["source_values"][1] == "Gamme montante développé épaules"
    assert gym.imported_history(first[0]["exercise_id"])[0]["weights_kg"] == [10]
    assert gym.imported_history(second[0]["exercise_id"])[0]["weights_kg"] == [15]
    original = copy.deepcopy(program)
    assert gym.repair_program(program) == original
    assert db.record("gym_program", program["id"]) == original
    workout = gym.start(program["id"], program["days"][1]["id"])
    ramp, work = workout["exercises"]
    assert ramp["canonical_name"] == "Échauffement · Développé couché incliné"
    assert "Échauffement pour Développé couché incliné" in ramp["training_instruction"]
    assert [s["reps"] for s in ramp["logged_sets"]] == [12, 8, 5]
    assert [s["weight"] for s in ramp["logged_sets"]] == [15, None, None]
    assert not any(s["done"] for s in ramp["logged_sets"])
    assert work["canonical_name"] == "Développé couché incliné"


def test_reanalyse_is_idempotent_and_preserves_row_ids_and_history(workspace):
    program = imported()
    before = [(e["id"], e["exercise_id"]) for d in program["days"] for e in d["exercises"]]
    count = len(db.records("gym_excel_history", 100))
    updated = gym.reanalyse(program["id"], program["revision"])
    assert [(e["id"], e["exercise_id"]) for d in updated["days"] for e in d["exercises"]] == before
    assert len(db.records("gym_excel_history", 100)) == count
    for d in updated["days"]:
        assert d["exercises"][0]["warmup_for_id"] == d["exercises"][1]["id"]


def test_no_target_is_not_guessed_from_other_session_document_or_hidden_row(workspace):
    for rows in [
        [item("ramp", "Gamme montante")],
        [item("ramp", "Gamme montante"), item("doc", "Fiche abdos")],
        [item("ramp", "Gamme montante"), {**item("next", "Squat"), "hidden": True}],
    ]:
        resolved = gym_warmups.resolve(rows)
        assert resolved[0]["warmup_for_id"] is None
        assert resolved[0]["warmup_target_name"] is None
        assert resolved[0]["name"] == "Gamme montante"
        view = exercise_catalog.decorate(resolved[0])
        assert view["catalog_id"] is None
        assert "à préciser" in view["training_instruction"]
    edited = [item("ramp", "Gamme montante Squat"), item("next", "Rowing")]
    edited[0]["edits"] = {"name": "Gamme montante Squat"}
    assert gym_warmups.resolve(edited)[0]["name"] == "Gamme montante Squat"


def test_existing_workout_actual_ids_and_logs_remain_untouched(workspace):
    program = imported()
    rows = copy.deepcopy(program["days"][1]["exercises"])
    ramp = rows[0]
    ramp["exercise_id"] = "legacy-shared-ramp"
    ramp["name"] = "Gamme montante développé épaules"
    for e in rows:
        e["logged_sets"] = [{"weight": 17.5, "reps": 8, "seconds": None, "done": True}]
    value = {
        "id": "old",
        "program_id": program["id"],
        "display_version": 2,
        "suggestions_applied": True,
        "started_at": "2026-01-01T12:00:00Z",
        "finished_at": None,
        "revision": 1,
        "exercises": rows,
    }
    db.upsert_record("gym_workout", "old", value)
    before = db.record("gym_workout", "old")
    view = gym.workout_view(value)
    assert db.record("gym_workout", "old") == before
    assert view["exercises"][0]["exercise_id"] == "legacy-shared-ramp"
    assert (
        view["exercises"][0]["catalogue_exercise_id"]
        == program["days"][1]["exercises"][0]["exercise_id"]
    )
    assert view["exercises"][0]["canonical_name"] == "Échauffement · Développé couché incliné"
    assert view["exercises"][0]["logged_sets"] == before["exercises"][0]["logged_sets"]


def test_history_never_pools_warmups_with_work_even_when_catalogue_matches(workspace):
    program = imported()
    ramp, work = program["days"][0]["exercises"]
    for e in [ramp, work]:
        db.upsert_record(
            "gym_binding",
            e["exercise_id"],
            {
                "exercise_id": e["exercise_id"],
                "catalog_id": "repdb:synthetic-shoulder",
                "weight_convention": "total",
                "weight_context": "",
                "method": "confirmed",
                "revision": 1,
            },
        )
    assert exercise_catalog.compatible_ids(ramp["exercise_id"]) == [ramp["exercise_id"]]
    assert ramp["exercise_id"] not in exercise_catalog.compatible_ids(work["exercise_id"])
    with user_scope("another-owner"):
        assert not db.record("gym_program", program["id"])


def test_workout_snapshot_does_not_follow_later_program_changes(workspace):
    program = imported()
    workout = gym.start(program["id"], program["days"][1]["id"])
    stored = db.record("gym_workout", workout["id"])
    program["days"][1]["exercises"][1]["name"] = "Rowing"
    db.upsert_record("gym_program", program["id"], program)
    result = gym.workout_view(stored)
    assert result["exercises"][0]["warmup_target_name"] == "Développé couché incliné"
    assert db.record("gym_workout", workout["id"]) == stored


def test_explicit_edit_removes_automatic_target_without_losing_source(workspace):
    source = [item("ramp", "Gamme montante"), item("work", "Squat")]
    resolved = gym_warmups.resolve(source)
    resolved[0].update(
        name="Échauffement personnalisé", edits={"name": "Échauffement personnalisé"}
    )
    edited = gym_warmups.resolve(resolved)[0]
    assert edited["name"] == "Échauffement personnalisé"
    assert edited["source_name"] == "Gamme montante"
    assert "warmup_for_id" not in edited
