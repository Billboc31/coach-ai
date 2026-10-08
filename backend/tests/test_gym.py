import base64
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from coach import api, db, gym
from coach.secrets import write_secret


def workbook_bytes():
    """Synthetic OOXML fixture; no user workbook or exercise history in this repository."""

    def cell(ref, value, kind="inlineStr", style=""):
        from xml.sax.saxutils import escape

        content = (
            f"<is><t>{escape(str(value))}</t></is>" if kind == "inlineStr" else f"<v>{value}</v>"
        )
        return f'<c r="{ref}" t="{kind}" {style}>{content}</c>'

    rows = {
        1: [
            ("C1", "ordre"),
            ("D1", "Exercices"),
            ("E1", "Tempo"),
            ("F1", "Rep"),
            ("G1", "Série"),
            ("I1", "R"),
            ("K1", "Poids"),
            ("L1", "Performance"),
            ("R1", "Consignes"),
            ("V1", "Lien vidéo"),
        ],
        3: [("K3", "SEMAINE 1")],
        4: [("D4", "Séance 1 : Exemple")],
        5: [
            ("C5", "A"),
            ("D5", "Exercice Alpha"),
            ("F5", "8"),
            ("G5", "3"),
            ("I5", "90 s"),
            ("L5", "40"),
            ("M5", "42"),
            ("V5", "Démonstration"),
        ],
        6: [("C6", "B"), ("D6", "Exercice Bêta"), ("L6", "X")],
        7: [("D7", "Séance 2 : Exemple")],
        8: [
            ("C8", "A"),
            ("D8", "Exercice Alpha"),
            ("F8", "10"),
            ("G8", "2"),
            ("K8", "0"),
            ("L8", "55"),
        ],
    }
    body = "".join(
        f'<row r="{r}">'
        + "".join(cell(ref, v) for ref, v in values)
        + (cell("F6", 46000, "n", 's="1"') if r == 6 else "")
        + "</row>"
        for r, values in rows.items()
    )
    parts = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Cycle exemple" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font/></fonts><fills count="1"><fill><patternFill/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf/><xf numFmtId="14"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
        "xl/worksheets/sheet1.xml": f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheetData>{body}</sheetData><mergeCells count="3"><mergeCell ref="G5:G6"/><mergeCell ref="I5:I6"/><mergeCell ref="L1:Q1"/></mergeCells><hyperlinks><hyperlink ref="V5" r:id="rId1"/></hyperlinks></worksheet>',
        "xl/worksheets/_rels/sheet1.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://youtu.be/12345678901" TargetMode="External"/></Relationships>',
    }
    binary = io.BytesIO()
    with zipfile.ZipFile(binary, "w", zipfile.ZIP_DEFLATED) as z:
        for name, value in parts.items():
            z.writestr(
                zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0)),
                value,
                compress_type=zipfile.ZIP_DEFLATED,
            )
    return binary.getvalue()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    return tmp_path


def imported(kg=False):
    p = gym.preview("example.xlsx", base64.b64encode(workbook_bytes()).decode())
    s = p["sheets"][0]
    body = gym.ImportSelection(
        title="Example program",
        performances_are_kg=kg,
        sheets=[gym.SheetMapping(name=s["name"], header=s["header"], mapping=s["mapping"])],
    )
    return p, gym.confirm(p["id"], body), body


def test_preview_mapping_merged_cells_history_and_repeat_import(workspace):
    preview, program, selection = imported()
    assert len(program["days"]) == 2
    alpha, beta = program["days"][0]["exercises"]
    assert alpha["sets"] == beta["sets"] == 3
    assert beta["rest"] == "90 s" and beta["warnings"]
    assert beta["reps"].startswith("2025") or beta["reps"].startswith("2026")
    assert gym.imported_history(alpha["exercise_id"])[0]["weights_kg"] is None
    assert alpha["media_url"] == "https://youtu.be/12345678901"
    assert gym.confirm(preview["id"], selection)["days"][0]["id"] == program["days"][0]["id"]
    assert (
        gym.preview("example.xlsx", base64.b64encode(workbook_bytes()).decode())["id"]
        == preview["id"]
    )
    assert program["source_sheets"][0]["rows"][5][6] == ""  # Source remains unfilled.
    assert gym.overview()["programs"][0]["days"][1]["exercises"][0]["weight"] == 0


def test_workout_actual_sets_revision_finish_and_reference(workspace):
    _, p, _ = imported(kg=True)
    w = gym.start(p["id"], p["days"][0]["id"])
    assert all(not s["done"] for e in w["exercises"] for s in e["logged_sets"])
    e = w["exercises"][0]
    assert e["excel_history"][0]["weights_kg"] is not None
    assert e["logged_sets"][0]["weight"] == e["excel_history"][0]["weights_kg"][0]
    assert e["logged_sets"][0]["reps"] == int(e["reps"])
    sets = {x["id"]: x["logged_sets"] for x in w["exercises"]}
    sets[e["id"]][0] = {"weight": 0, "reps": 8, "done": True}
    update = gym.WorkoutUpdate(revision=1, sets=sets)
    saved = gym.update_workout(w["id"], update)
    assert saved["revision"] == 2
    with pytest.raises(gym.Conflict):
        gym.update_workout(w["id"], update)
    complete = gym.update_workout(w["id"], gym.WorkoutUpdate(revision=2, sets=sets, finish=True))
    assert complete["finished_at"]
    with pytest.raises(gym.Conflict):
        gym.update_workout(w["id"], gym.WorkoutUpdate(revision=3, sets=sets))
    next_workout = gym.start(p["id"], p["days"][1]["id"])
    assert next_workout["exercises"][0]["reference"]["sets"][0]["weight"] == 0
    assert gym.history(e["exercise_id"])[0]["sets"][0]["reps"] == 8
    assert gym.context()[0]["completed"] is False


def test_workout_seconds_and_invalid_series_do_not_overwrite(workspace):
    _, p, _ = imported()
    w = gym.start(p["id"], p["days"][0]["id"])
    sets = {x["id"]: x["logged_sets"] for x in w["exercises"]}
    sets[w["exercises"][0]["id"]][0]["done"] = True
    sets[w["exercises"][0]["id"]][0]["reps"] = None
    with pytest.raises(ValueError):
        gym.update_workout(w["id"], gym.WorkoutUpdate(revision=1, sets=sets))
    assert db.record("gym_workout", w["id"])["revision"] == 1
    sets[w["exercises"][0]["id"]][0]["seconds"] = 30
    assert gym.update_workout(w["id"], gym.WorkoutUpdate(revision=1, sets=sets))["revision"] == 2
    bad = gym.WorkoutUpdate(revision=2, sets={"bad": []})
    with pytest.raises(ValueError):
        gym.update_workout(w["id"], bad)


def test_owner_scoping_and_video_url_validation(workspace, monkeypatch):
    _, p, _ = imported()
    eid = p["days"][0]["exercises"][0]["exercise_id"]
    assert (
        gym.set_video(eid, "https://www.youtube.com/watch?v=12345678901")["video_id"]
        == "12345678901"
    )
    for url in [
        "http://youtu.be/12345678901",
        "https://attacker.example/watch?v=12345678901",
        "https://youtube.com.evil.example/watch?v=12345678901",
    ]:
        with pytest.raises(ValueError):
            gym.set_video(eid, url)
    assert gym.safe_media("javascript:alert(1)") is None
    monkeypatch.setattr(db, "user_id", lambda: "another")
    with pytest.raises(ValueError):
        gym.start(p["id"], p["days"][0]["id"])
    assert gym.set_video(eid, "") is None


def test_invalid_file_and_private_api(workspace):
    with pytest.raises(ValueError):
        gym.preview("old.xls", "AA==")
    with pytest.raises(ValueError):
        gym.preview("file.xlsx", "not-base64")
    write_secret(workspace / "app.json", {"access_key": "test-key"})
    api.sessions.clear()
    api.login_attempts.clear()
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as c:
        assert c.get("/api/gym").status_code == 401
        assert c.post("/api/gym/import", json={}).status_code == 401
        c.post("/api/login", json={"access_key": "test-key"})
        assert (
            c.post("/api/gym/import", json={"filename": "bad.xlsx", "base64": "bad"}).status_code
            == 422
        )
        preview = c.post(
            "/api/gym/import",
            json={
                "filename": "example.xlsx",
                "base64": base64.b64encode(workbook_bytes()).decode(),
            },
        ).json()
        s = preview["sheets"][0]
        p = c.post(
            "/api/gym/import/" + preview["id"] + "/confirm",
            json={
                "title": "Example",
                "sheets": [{"name": s["name"], "header": s["header"], "mapping": s["mapping"]}],
            },
        ).json()
        assert c.get("/api/gym/programs/" + p["id"] + "/source").status_code == 200
        assert c.get("/api/gym/programs/" + p["id"] + "/download").content == workbook_bytes()
        w = c.post(
            "/api/gym/workouts", json={"program_id": p["id"], "day_id": p["days"][0]["id"]}
        ).json()
        assert c.get("/api/gym/workouts/" + w["id"]).json()["revision"] == 1
        assert (
            c.get("/api/gym/exercises/" + w["exercises"][0]["exercise_id"] + "/history").json()[
                "sessions"
            ]
            == []
        )
        assert (
            c.post(
                "/api/gym/workouts", json={"program_id": p["id"], "day_id": "unknown"}
            ).status_code
            == 422
        )
        assert c.get("/api/gym/workouts/unknown").status_code == 404
        assert (
            c.post(
                "/api/gym/import", json={}, headers={"Origin": "https://bad.example"}
            ).status_code
            == 403
        )


def test_performance_x_keeps_row_weight_and_unknown_reps():
    entry = gym.performance_view({"performance": ["5", "x", "X", "X"]})
    assert entry["weights_kg"] == [5, 5, 5, 5]
    assert all(s["success"] and s["reps"] is None for s in entry["performance_sets"])
    assert entry["performance"] == ["5", "x", "X", "X"]
    entry = gym.performance_view({"performance": ["X", "0", "", "X", "7,5 kg", "X"]})
    assert entry["weights_kg"] == [None, 0, None, 0, 7.5, 7.5]
    assert not entry["performance_sets"][2]["success"]
    assert gym.performance_view({"performance": ["X"]})["weights_kg"] == [None]
    assert (
        gym.performance_view({"performance": ["5", "X"], "performances_are_kg": False})[
            "weights_kg"
        ]
        is None
    )


def labelled_workbook():
    from datetime import datetime

    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Cycle  exemple"
    sheet.append(["Exercice", "Rep", "Série", "Performance", "", "", "", "Notes"])
    sheet.append(
        ["Exercice Alpha", datetime(2026, 10, 10), datetime(2026, 3, 2), 5, "x", "X", "X", "Texte"]
    )
    sheet["B2"].number_format = sheet["C2"].number_format = "d/m"
    sheet.append(["Exercice Beta", "12\n12", 3, "X", "", 8, "X"])
    sheet.merge_cells("D1:G1")
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def test_excel_labels_and_performance_positions(workspace):
    preview = gym.preview("labels.xlsx", base64.b64encode(labelled_workbook()).decode())
    sheet = preview["sheets"][0]
    p = gym.confirm(
        preview["id"],
        gym.ImportSelection(
            title="Labels",
            sheets=[gym.SheetMapping(**{k: sheet[k] for k in ("name", "header", "mapping")})],
        ),
    )
    a, b = p["days"][0]["exercises"]
    assert a["reps"] == "10/10" and a["sets_label"] == "2/3"
    assert a["sets"] is None and not a["warnings"]
    assert b["reps"] == "12\n12"
    assert b["performance"] == ["X", "", "8", "X"]
    assert gym.imported_history(a["exercise_id"])[0]["weights_kg"] == [5] * 4
    assert gym.imported_history(b["exercise_id"])[0]["weights_kg"] == [None, None, 8, 8]
    assert p["source_sheets"][0]["rows"][1][1] == "2026-10-10 00:00:00"


def test_legacy_program_repair_keeps_actual_sessions(workspace):
    preview = gym.preview("labels.xlsx", base64.b64encode(labelled_workbook()).decode())
    sheet = preview["sheets"][0]
    p = gym.confirm(
        preview["id"],
        gym.ImportSelection(
            title="Labels",
            sheets=[gym.SheetMapping(**{k: sheet[k] for k in ("name", "header", "mapping")})],
        ),
    )
    # Simulate the old parser's stored program and workout snapshot.
    p.pop("display_version")
    a = p["days"][0]["exercises"][0]
    a["reps"] = "2026-10-10 00:00:00"
    a.pop("sets_label")
    a["warnings"] = [
        "reps: cellule Excel de type date, à vérifier.",
        "sets: cellule Excel de type date, à vérifier.",
    ]
    db.upsert_record("gym_program", p["id"], p)
    w = {
        "id": "legacy",
        "program_id": p["id"],
        "revision": 7,
        "finished_at": db.now(),
        "started_at": db.now(),
        "exercises": [
            {
                **a,
                "logged_sets": [{"weight": 0, "reps": 6, "seconds": None, "done": True}],
                "excel_history": [{"performance": ["5", "X", "X", "X"], "weights_kg": None}],
            }
        ],
    }
    db.upsert_record("gym_workout", w["id"], w)
    view = gym.overview()
    repaired = view["programs"][0]["days"][0]["exercises"][0]
    assert repaired["id"] == a["id"] and repaired["reps"] == "10/10"
    assert repaired["sets_label"] == "2/3" and not repaired["warnings"]
    result = gym.workout_view(db.record("gym_workout", "legacy"))
    assert result["exercises"][0]["reps"] == "10/10"
    assert result["exercises"][0]["excel_history"][0]["weights_kg"] == [5] * 4
    assert result["revision"] == 7 and result["finished_at"] == w["finished_at"]
    assert db.record("gym_workout", "legacy") == w
    assert gym.overview()["programs"][0]["days"][0]["exercises"][0] == repaired


def action(program, name, **extra):
    return gym.manage_program(
        program["id"], gym.ProgramAction(revision=program.get("revision", 1), action=name, **extra)
    )


def test_program_removal_restore_keeps_sessions_and_original(workspace):
    _, p, _ = imported(True)
    day = p["days"][0]
    item = day["exercises"][0]
    w = gym.start(p["id"], day["id"])
    stored_workout = db.record("gym_workout", w["id"])
    original = db.record("gym_source", p["id"])
    p = action(p, "hide_exercise", day_id=day["id"], exercise_id=item["id"])
    assert len(gym.start(p["id"], day["id"])["exercises"]) == 1
    p = action(p, "restore_exercise", day_id=day["id"], exercise_id=item["id"])
    assert len(gym.start(p["id"], day["id"])["exercises"]) == 2
    for hide, restore, extra in [
        ("hide_day", "restore_day", {"day_id": day["id"]}),
        ("hide_sheet", "restore_sheet", {"sheet": day["sheet"]}),
        ("archive", "restore_program", {}),
    ]:
        p = action(p, hide, **extra)
        with pytest.raises(ValueError):
            gym.start(p["id"], day["id"])
        assert db.record("gym_workout", w["id"]) == stored_workout
        p = action(p, restore, **extra)
        assert gym.start(p["id"], day["id"])["exercises"][0]["id"] == item["id"]
    assert db.record("gym_source", p["id"]) == original


def test_reanalysis_retains_edits_ids_removals_and_history(workspace):
    _, p, _ = imported(True)
    day = p["days"][0]
    item = day["exercises"][0]
    w = gym.start(p["id"], day["id"])
    stored_workout = db.record("gym_workout", w["id"])
    body = gym.ExerciseEdit(
        revision=p["revision"],
        name="Exercice corrigé",
        sets=4,
        reps="10/10",
        weight=0,
        rest="120 s",
        tempo="3010",
        notes="Consigne",
        illustration="row",
    )
    p = gym.edit_exercise(p["id"], day["id"], item["id"], body)
    p = action(p, "hide_sheet", sheet=day["sheet"])
    count = len(db.records("gym_excel_history", 100))
    source = db.record("gym_source", p["id"])
    for _ in range(2):
        previous_revision = p["revision"]
        p = gym.reanalyse(p["id"], previous_revision)
        assert p["revision"] == previous_revision + 1
        rebuilt = p["days"][0]["exercises"][0]
        assert p["days"][0]["id"] == day["id"] and rebuilt["id"] == item["id"]
        assert rebuilt["name"] == "Exercice corrigé" and rebuilt["reps"] == "10/10"
        assert rebuilt["sets"] == 4 and rebuilt["weight"] == 0 and rebuilt["illustration"] == "row"
        assert p["hidden_sheets"] == [day["sheet"]]
        assert len(db.records("gym_excel_history", 100)) == count
        assert db.record("gym_workout", w["id"]) == stored_workout
        assert gym.workout_view(w)["exercises"][0]["reps"] == item["reps"]
        assert db.record("gym_source", p["id"]) == source


def test_legacy_reanalysis_restores_raw_positions_without_duplicates(workspace):
    preview = gym.preview("labels.xlsx", base64.b64encode(labelled_workbook()).decode())
    sheet = preview["sheets"][0]
    p = gym.confirm(
        preview["id"],
        gym.ImportSelection(
            title="Labels",
            sheets=[gym.SheetMapping(**{k: sheet[k] for k in ("name", "header", "mapping")})],
        ),
    )
    # Simulate legacy collapsed performance and date labels; history IDs came from that parser.
    p.pop("selection")
    p.pop("revision")
    p.pop("display_version")
    with db.connection() as conn:
        from sqlalchemy import text

        conn.execute(
            text("DELETE FROM records WHERE user_id=:u AND kind='gym_excel_history'"),
            {"u": "local"},
        )
    import hashlib
    import json

    for item in p["days"][0]["exercises"]:
        item.pop("imported_history_id")
        item["performance"] = [v for v in item["performance"] if v]
        if item["name"] == "Exercice Alpha":
            item["reps"] = "2026-10-10 00:00:00"
        key = hashlib.sha256(
            json.dumps(
                [
                    p["source"],
                    item["sheet"],
                    item["source_row"],
                    item["exercise_id"],
                    item["performance"],
                    item["reps"],
                ],
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        db.upsert_record(
            "gym_excel_history",
            key,
            {
                "id": key,
                "exercise_id": item["exercise_id"],
                "sheet": item["sheet"],
                "row": item["source_row"],
                "performance": item["performance"],
                "reps": item["reps"],
                "imported_at": db.now(),
            },
        )
    db.upsert_record("gym_program", p["id"], p)
    for expected_revision in (1, 2):
        p = gym.reanalyse(p["id"], expected_revision)
        assert p["revision"] == expected_revision + 1
        assert p["days"][0]["exercises"][0]["reps"] == "10/10"
        assert p["days"][0]["exercises"][1]["performance"] == ["X", "", "8", "X"]
        assert len(db.records("gym_excel_history", 100)) == 2


def test_program_mutations_validate_revision_ownership_and_fields(workspace, monkeypatch):
    _, p, _ = imported()
    day = p["days"][0]
    old = p
    p = action(p, "hide_day", day_id=day["id"])
    with pytest.raises(gym.Conflict):
        action(old, "archive")
    with pytest.raises(gym.Conflict):
        gym.reanalyse(p["id"], 1)
    with pytest.raises(ValueError):
        action(p, "hide_sheet", sheet="Unknown")
    with pytest.raises(ValueError):
        gym.ExerciseEdit(revision=1, name="Alpha", sets=0)
    monkeypatch.setattr(db, "user_id", lambda: "other")
    assert action(p, "archive") is None
    assert gym.reanalyse(p["id"], p["revision"]) is None
    assert (
        gym.edit_exercise(
            p["id"],
            day["id"],
            day["exercises"][0]["id"],
            gym.ExerciseEdit(revision=p["revision"], name="Alpha"),
        )
        is None
    )


def test_program_api_edit_reanalyse_remove_security(workspace):
    write_secret(workspace / "app.json", {"access_key": "test-key"})
    api.sessions.clear()
    api.login_attempts.clear()
    _, p, _ = imported(True)
    path = "/api/gym/programs/" + p["id"]
    with TestClient(api.app, headers={"Origin": "http://localhost:8000"}) as c:
        assert c.post(path + "/reanalyse", json={"revision": 1}).status_code == 401
        c.post("/api/login", json={"access_key": "test-key"})
        assert (
            c.post(
                path + "/manage",
                json={"revision": 1, "action": "archive"},
                headers={"Origin": "https://bad.example"},
            ).status_code
            == 403
        )
        day = p["days"][0]
        item = day["exercises"][0]
        edit = c.put(
            path + "/days/" + day["id"] + "/exercises/" + item["id"],
            json={"revision": 1, "name": "Alpha", "sets": 2, "reps": "8", "weight": 0},
        ).json()
        assert edit["revision"] == 2
        assert c.post(path + "/reanalyse", json={"revision": 1}).status_code == 409
        rebuilt = c.post(path + "/reanalyse", json={"revision": 2}).json()
        assert rebuilt["revision"] == 3 and rebuilt["days"][0]["exercises"][0]["name"] == "Alpha"
        assert c.post(path + "/manage", json={"revision": 3, "action": "archive"}).json()[
            "archived"
        ]
        assert (
            c.post(
                "/api/gym/workouts", json={"program_id": p["id"], "day_id": day["id"]}
            ).status_code
            == 422
        )
        assert (
            c.post("/api/gym/programs/unknown/reanalyse", json={"revision": 1}).status_code == 404
        )


def test_rename_titles_survive_refresh_and_keep_source_names(workspace):
    _, p, _ = imported(True)
    day = p["days"][0]
    key = p["id"]
    p = gym.rename_program_item(
        key, gym.ProgramTitle(revision=p["revision"], title="Mon programme")
    )
    p = gym.rename_program_item(
        key, gym.ProgramTitle(revision=p["revision"], sheet=day["sheet"], title="Mon cycle")
    )
    p = gym.rename_program_item(
        key, gym.ProgramTitle(revision=p["revision"], day_id=day["id"], title="Ma séance")
    )
    p = gym.reanalyse(key, p["revision"])
    assert p["title"] == "Mon programme"
    assert p["sheet_titles"][day["sheet"]] == "Mon cycle"
    assert p["days"][0]["sheet"] == day["sheet"]
    assert p["days"][0]["name"] == day["name"]
    assert gym.start(key, day["id"])["title"] == "Ma séance"


def test_linked_routine_is_read_projection_with_original_ids_and_logs(workspace):
    _, program, _ = imported()
    day = program["days"][0]
    item = day["exercises"][0]
    item["name"] = "Fiche mobilité"
    sheet = next(s for s in program["source_sheets"] if s["name"] == item["sheet"])
    sheet["links"] = {
        f"{item['source_row']}:21": "https://1drv.ms/i/synthetic-routine",
        f"{item['source_row']}:4": "javascript:alert(1)",
        "999:21": "https://1drv.ms/i/another-row",
    }
    db.upsert_record("gym_program", program["id"], program)
    before = db.record("gym_program", program["id"])
    view = gym.overview()["programs"][0]["days"][0]["exercises"][0]
    assert view["is_document"] and "https://1drv.ms/i/synthetic-routine" in view["document_links"]
    assert all(link.startswith("https://") for link in view["document_links"])
    assert view["id"] == item["id"] and view["exercise_id"] == item["exercise_id"]
    assert db.record("gym_program", program["id"]) == before
    started = gym.start(program["id"], day["id"])
    exercise = started["exercises"][0]
    assert exercise["document_links"] == view["document_links"]
    assert all(s["weight"] is None and s["reps"] is None for s in exercise["logged_sets"])
    # The document reference survives even if its programme source is later absent.
    preserved = gym.document_view(exercise, {})
    assert preserved["document_links"] == view["document_links"]


def test_progressive_weight_instruction_does_not_invent_weights(workspace):
    from coach import exercise_catalog

    item = {
        "exercise_id": "synthetic-progression",
        "name": "gamme montante presse oblique",
        "weight": None,
        "reps": "10",
        "performance": ["X", "X"],
    }
    result = exercise_catalog.decorate(item)
    assert result["movement_name"] == "presse oblique"
    assert "progressive" in result["training_instruction"]
    assert result["name"] == item["name"] and result["weight"] is None
    assert result["performance"] == item["performance"]
