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
    assert all(
        s["weight"] is None and not s["done"] for e in w["exercises"] for s in e["logged_sets"]
    )
    e = w["exercises"][0]
    assert e["excel_history"][0]["weights_kg"] is not None
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
