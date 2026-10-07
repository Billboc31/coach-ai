"""Excel preview, explicit column mapping and persistent workout set logs."""

import base64
import hashlib
import io
import json
import re
import threading
import unicodedata
import uuid
import zipfile
from urllib.parse import parse_qs, urlparse

from openpyxl import load_workbook
from pydantic import BaseModel, Field
from sqlalchemy import text

from coach import db
from coach.config import user_id

lock = threading.RLock()
MAX_FILE = 5 * 1024 * 1024


def normalized(value):
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(value).lower()) if not unicodedata.combining(c)
    ).strip()


def video_id(url):
    if not url:
        return None
    p = urlparse(url)
    if p.scheme != "https":
        raise ValueError("Lien YouTube HTTPS attendu.")
    host = p.hostname or ""
    if host == "youtu.be":
        key = p.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        key = parse_qs(p.query).get("v", [""])[0]
        if p.path.startswith(("/embed/", "/shorts/")):
            key = p.path.split("/")[2]
    else:
        raise ValueError("Lien YouTube attendu.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", key):
        raise ValueError("Lien vidéo YouTube invalide.")
    return key


ALIASES = {
    "name": ["exercice", "exercise", "exercices", "nom"],
    "sets": ["series", "sets", "serie"],
    "reps": ["repetitions", "reps", "rep"],
    "weight": ["poids", "charge", "kg", "poids kg", "charge kg", "poids e"],
    "rest": ["repos", "rest", "recuperation"],
    "notes": ["consignes", "notes", "tempo"],
    "video": ["video", "youtube", "lien video"],
}


def display_cell(cell):
    """Restore Excel's day/month labels without treating them as measured reps."""
    value = cell.value
    fmt = cell.number_format.lower()
    if getattr(cell, "is_date", False) and fmt in {"d/m", "dd/mm", "d/mm", "dd/m"}:
        day = str(value.day).zfill(2) if fmt.startswith("dd") else str(value.day)
        month = str(value.month).zfill(2) if fmt.endswith("mm") else str(value.month)
        return day + "/" + month
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value) if value is not None else ""


def performance_view(entry):
    last_weight = None
    decoded = []
    kg = entry.get("performances_are_kg", True)
    for raw in entry.get("performance", []):
        value = str(raw).strip()
        weight = numeric(value, kg=True) if kg else None
        success = value.lower() == "x" or weight is not None
        if weight is not None:
            last_weight = weight
        elif value.lower() == "x":
            weight = last_weight
        decoded.append({"raw": raw, "weight": weight, "success": success, "reps": None})
    return {
        **entry,
        "performance_sets": decoded,
        "weights_kg": [v["weight"] for v in decoded] if kg else None,
    }


def repair_program(program):
    """Repair old display labels in place; preserve IDs and all actual workout logs."""
    if not program or program.get("display_version") == 2:
        return program
    source = db.record("gym_source", program["id"])
    if not source:
        return program
    book = load_workbook(io.BytesIO(base64.b64decode(source["base64"])), keep_links=False)
    try:
        for day in program["days"]:
            for item in day["exercises"]:
                if item["sheet"] not in book.sheetnames:
                    continue
                sheet = book[item["sheet"]]
                row = item["source_row"]
                repaired = set()
                saved_sheet = next(
                    (v for v in program.get("source_sheets", []) if v["name"] == item["sheet"]), {}
                )
                col = saved_sheet.get("mapping", {}).get("sets")
                if col is not None and "sets_label" not in item:
                    cell = sheet.cell(row, col + 1)
                    for merged in sheet.merged_cells.ranges:
                        if cell.coordinate in merged and merged.min_col == merged.max_col:
                            cell = sheet.cell(merged.min_row, merged.min_col)
                            break
                    item["sets_label"] = display_cell(cell)
                    if getattr(cell, "is_date", False) and item["sets_label"] != str(cell.value):
                        repaired.add("sets")
                for field in ("reps", "rm", "rest", "short_rest", "tempo", "sets_label"):
                    original = item.get(field, "")
                    if not original:
                        continue
                    matches = [c for c in sheet[row] if str(c.value) == original]
                    values = {display_cell(c) for c in matches}
                    if len(values) == 1:
                        item[field] = values.pop()
                        if item[field] != original:
                            repaired.add(field)
                item["warnings"] = [
                    w for w in item.get("warnings", []) if w.split(":", 1)[0] not in repaired
                ]
        program["display_version"] = 2
        db.upsert_record("gym_program", program["id"], program)
    finally:
        book.close()
    return program


def workout_view(value):
    if not value:
        return value
    program = repair_program(db.record("gym_program", value["program_id"]))
    items = {e["id"]: e for d in (program or {}).get("days", []) for e in d["exercises"]}
    exercises = []
    for exercise in value["exercises"]:
        item = items.get(exercise["id"], {})
        labels = {
            k: item[k]
            for k in ("reps", "rm", "rest", "short_rest", "tempo", "sets_label", "warnings")
            if k in item and value.get("display_version") != 2
        }
        exercises.append(
            {
                **exercise,
                **labels,
                "excel_history": [performance_view(h) for h in exercise.get("excel_history", [])],
            }
        )
    return {**value, "exercises": exercises}


def preview(filename, encoded, *, refresh=False):
    if not filename.lower().endswith(".xlsx"):
        raise ValueError("Choisir un fichier .xlsx ; convertir les anciens .xls dans Excel.")
    try:
        binary = base64.b64decode(encoded, validate=True)
        if len(binary) > MAX_FILE:
            raise ValueError()
        with zipfile.ZipFile(io.BytesIO(binary)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(e.file_size for e in entries) > 30 * 1024 * 1024:
                raise ValueError()
        workbook = load_workbook(
            io.BytesIO(binary), read_only=False, data_only=False, keep_links=False
        )
    except Exception:
        raise ValueError("Fichier Excel invalide ou trop volumineux (5 Mo maximum).") from None
    sheets = []
    try:
        if len(workbook.worksheets) > 30:
            raise ValueError("30 feuilles maximum.")
        for sheet in workbook.worksheets[:30]:
            rows = []
            if sheet.max_row > 1000 or sheet.max_column > 40:
                raise ValueError("1000 lignes et 40 colonnes maximum par feuille.")
            links, dates, display_rows = {}, [], []
            for i, cells in enumerate(sheet.iter_rows()):
                row = [c.value for c in cells]
                for c in cells:
                    if c.hyperlink:
                        links[f"{c.row}:{c.column - 1}"] = c.hyperlink.target
                    if getattr(c, "is_date", False):
                        dates.append(f"{c.row}:{c.column - 1}")
                if i == 1000:
                    raise ValueError(
                        "Une feuille dépasse 1000 lignes. Réduis le fichier avant import."
                    )
                display_rows.append([display_cell(c) for c in cells])
                rows.append([str(v) if v is not None else "" for v in row])
            while rows and not any(rows[-1]):
                rows.pop()
            display_rows = display_rows[: len(rows)]
            expanded = [list(row) for row in display_rows]
            for merged in sheet.merged_cells.ranges:
                if merged.min_col == merged.max_col and merged.min_row <= len(rows):
                    col = merged.min_col - 1
                    for j in range(merged.min_row, min(merged.max_row, len(rows))):
                        expanded[j][col] = display_rows[merged.min_row - 1][col]
            best = 0
            mapping = {}
            for i, row in enumerate(rows[:30]):
                candidate = {
                    field: next(
                        (col for col, value in enumerate(row) if normalized(value) in names), None
                    )
                    for field, names in ALIASES.items()
                }
                if candidate.get("name") is not None and sum(
                    v is not None for v in candidate.values()
                ) > len(mapping):
                    best, mapping = i, {k: v for k, v in candidate.items() if v is not None}
            if mapping:
                for col, value in enumerate(rows[best]):
                    label = normalized(value)
                    if label.startswith("consigne"):
                        mapping["notes"] = col
                    if value.strip() == "R":
                        mapping["rest"] = col
                    if value.strip() == "r":
                        mapping["short_rest"] = col
                    if label.startswith("lien video"):
                        mapping["video"] = col
                if mapping.get("order") == 2 and any(
                    normalized(row[1]) in {"echauf.", "echauf", "renfo"}
                    for row in rows[best + 1 : best + 30]
                ):
                    mapping["group"] = 1
            sheets.append(
                {
                    "name": sheet.title,
                    "rows": rows,
                    "expanded": expanded,
                    "display_rows": display_rows,
                    "links": links,
                    "date_cells": dates,
                    "header": best,
                    "mapping": mapping,
                }
            )
    finally:
        workbook.close()
    value = {
        "id": uuid.uuid4().hex,
        "filename": filename[:150],
        "sheets": sheets,
        "created_at": db.now(),
        "fingerprint": hashlib.sha256(binary).hexdigest(),
    }
    with db.connection() as conn:
        existing = conn.execute(
            text(
                "SELECT data FROM records WHERE user_id=:u AND kind='gym_import' "
                "AND json_extract(data,'$.fingerprint')=:f LIMIT 1"
            ),
            {"u": user_id(), "f": value["fingerprint"]},
        ).first()
    if existing:
        old = json.loads(existing[0])
        if not refresh:
            return old
        value.update(id=old["id"], program_id=old.get("program_id"), created_at=old["created_at"])
    db.upsert_record("gym_source", value["id"], {"filename": filename, "base64": encoded})
    db.upsert_record("gym_import", value["id"], value)
    return value


class SheetMapping(BaseModel):
    name: str = Field(max_length=100)
    header: int = Field(ge=0, le=999)
    mapping: dict[str, int] = Field(max_length=16)


class ImportSelection(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    performances_are_kg: bool = True
    sheets: list[SheetMapping] = Field(min_length=1, max_length=30)


def numeric(value, *, kg=False):
    if kg:
        value = re.sub(r"\s*kg\s*$", "", str(value), flags=re.I)
    try:
        parsed = float(str(value).replace(",", "."))
        return parsed if 0 <= parsed <= 2000 else None
    except ValueError:
        return None


def confirm(key, selection, *, rebuild=False):
    with lock:
        source = db.record("gym_import", key)
        if not source:
            return None
        if source.get("program_id") and not rebuild:
            return db.record("gym_program", source["program_id"])
        previous = db.record("gym_program", key) if rebuild else {}
        days = []
        imported = []
        exercises = {}
        for chosen in selection.sheets:
            sheet = next((s for s in source["sheets"] if s["name"] == chosen.name), None)
            if not sheet or chosen.header >= len(sheet["rows"]) or "name" not in chosen.mapping:
                raise ValueError(
                    "Choisir la ligne des titres et la colonne exercice pour chaque feuille."
                )
            if any(k not in ALIASES or not 0 <= v < 40 for k, v in chosen.mapping.items()):
                raise ValueError("Association de colonnes invalide.")
            items = []
            for index, row, label, week, session in workout_rows(sheet, chosen):

                def cell(field):
                    col = chosen.mapping.get(field)
                    return row[col].strip() if col is not None and col < len(row) else ""

                name = cell("name")
                if not name or name.startswith("="):
                    continue
                eid = hashlib.sha256(normalized(name).encode()).hexdigest()[:24]
                count = numeric(cell("sets"))
                count = (
                    int(count)
                    if count is not None and count.is_integer() and 1 <= count <= 20
                    else None
                )
                media = sheet.get("links", {}).get(
                    f"{index}:{chosen.mapping.get('video')}", cell("video")
                )
                try:
                    vid = video_id(media)
                except ValueError:
                    vid = None
                exercises[eid] = {"id": eid, "name": name[:200], "video_id": vid}
                perf_col = chosen.mapping.get("performance")
                perf = []
                if perf_col is not None:
                    end = next(
                        (
                            j
                            for j in range(perf_col + 1, len(row))
                            if sheet["rows"][chosen.header][j]
                        ),
                        len(row),
                    )
                    perf = list(row[perf_col:end])
                    while perf and not perf[-1].strip():
                        perf.pop()
                if perf:
                    imported.append(
                        {
                            "id": hashlib.sha256(
                                json.dumps(
                                    [
                                        source["filename"],
                                        chosen.name,
                                        index,
                                        eid,
                                        perf,
                                        cell("reps"),
                                    ],
                                    ensure_ascii=False,
                                ).encode()
                            ).hexdigest(),
                            "exercise_id": eid,
                            "source": "excel",
                            "program_id": key,
                            "sheet": chosen.name,
                            "week": week,
                            "session": session,
                            "row": index,
                            "performance": perf,
                            "reps": cell("reps"),
                            "performances_are_kg": selection.performances_are_kg,
                            "weights_kg": performance_view(
                                {
                                    "performance": perf,
                                    "performances_are_kg": selection.performances_are_kg,
                                }
                            )["weights_kg"],
                            "imported_at": db.now(),
                        }
                    )
                items.append(
                    {
                        "id": uuid.uuid4().hex,
                        "exercise_id": eid,
                        "name": name[:200],
                        "sets": count,
                        "sets_label": cell("sets"),
                        "reps": cell("reps"),
                        "weight": numeric(cell("weight"), kg=True),
                        "rest": cell("rest"),
                        "notes": cell("notes"),
                        "comments": cell("comments"),
                        "rm": cell("rm"),
                        "short_rest": cell("short_rest"),
                        "group": cell("group"),
                        "label": label,
                        "sheet": chosen.name,
                        "week": week,
                        "order": cell("order"),
                        "tempo": cell("tempo"),
                        "performance": perf,
                        "imported_history_id": imported[-1]["id"] if perf else None,
                        "media_url": safe_media(media),
                        "warnings": [
                            f"{field}: cellule Excel de type date, à vérifier."
                            for field in ("reps", "sets")
                            if f"{index}:{chosen.mapping.get(field)}" in sheet.get("date_cells", [])
                            and cell(field) == sheet["rows"][index - 1][chosen.mapping[field]]
                        ],
                        "source_row": index,
                        "source_values": sheet["rows"][index - 1],
                    }
                )
            grouped = {}
            for item in items:
                grouped.setdefault(item["label"], []).append(item)
            for label, group in grouped.items():
                days.append(
                    {
                        "id": uuid.uuid4().hex,
                        "name": label,
                        "sheet": chosen.name,
                        "week": group[0]["week"],
                        "exercises": group,
                    }
                )
        if not days:
            raise ValueError("Aucun exercice identifié. Vérifie les colonnes avant de confirmer.")
        program = {
            "id": key,
            "title": selection.title.strip(),
            "days": days,
            "created_at": db.now(),
            "source": source["filename"],
            "source_sheets": source["sheets"],
            "display_version": 2,
            "revision": previous.get("revision", 1) + 1 if previous else 1,
            "selection": selection.model_dump(),
        }
        if previous:
            program["created_at"] = previous["created_at"]
            program["hidden_sheets"] = previous.get("hidden_sheets", [])
            program["sheet_titles"] = previous.get("sheet_titles", {})
            program["archived"] = previous.get("archived", False)
            old_days = {(d["sheet"], d["week"], d["name"]): d for d in previous["days"]}
            old_items = {
                (e["sheet"], e["source_row"]): e for d in previous["days"] for e in d["exercises"]
            }
            for day in days:
                old_day = old_days.get((day["sheet"], day["week"], day["name"]))
                if old_day:
                    day.update(id=old_day["id"], hidden=old_day.get("hidden", False))
                    if old_day.get("display_name"):
                        day["display_name"] = old_day["display_name"]
                for item in day["exercises"]:
                    old_item = old_items.get((item["sheet"], item["source_row"]))
                    if old_item:
                        item.update(id=old_item["id"], hidden=old_item.get("hidden", False))
                        for field, value in old_item.get("edits", {}).items():
                            item[field] = value
                        item["edits"] = old_item.get("edits", {})
            # Reuse legacy history keys as well as modern keys; no duplicate rows on refresh.
            with db.connection() as conn:
                existing_keys = {
                    r[0]
                    for r in conn.execute(
                        text(
                            "SELECT record_key FROM records WHERE user_id=:u AND kind='gym_excel_history'"
                        ),
                        {"u": user_id()},
                    )
                }
            for entry in imported:
                old_item = old_items.get((entry["sheet"], entry["row"]))
                if not old_item:
                    continue
                candidates = [old_item.get("reps", ""), *old_item.get("source_values", [])]
                history_key = old_item.get("imported_history_id")
                if history_key in existing_keys:
                    existing = db.record("gym_excel_history", history_key)
                    entry.update(id=history_key, imported_at=existing["imported_at"])
                    continue
                for reps in candidates:
                    legacy_key = hashlib.sha256(
                        json.dumps(
                            [
                                previous["source"],
                                entry["sheet"],
                                entry["row"],
                                old_item["exercise_id"],
                                old_item.get("performance", []),
                                reps,
                            ],
                            ensure_ascii=False,
                        ).encode()
                    ).hexdigest()
                    if legacy_key in existing_keys:
                        existing = db.record("gym_excel_history", legacy_key)
                        entry["id"] = existing["id"]
                        entry["imported_at"] = existing["imported_at"]
                        break
        history_ids = {(h["sheet"], h["row"]): h["id"] for h in imported}
        for day in days:
            for item in day["exercises"]:
                item["imported_history_id"] = history_ids.get((item["sheet"], item["source_row"]))
        # Exercise history never gets replaced by re-importing a program.
        for eid, exercise in exercises.items():
            old = db.record("gym_exercise", eid)
            db.upsert_record(
                "gym_exercise",
                eid,
                {**exercise, "video_id": old.get("video_id") or exercise["video_id"]},
            )
        for entry in imported:
            db.upsert_record("gym_excel_history", entry["id"], entry)
        db.upsert_record("gym_program", key, program)
        db.upsert_record("gym_import", key, {**source, "program_id": key})
        return program


def history(exercise_id):
    with db.connection() as conn:
        rows = conn.execute(
            text(
                "SELECT w.data,e.value FROM records w, json_each(w.data,'$.exercises') e "
                "WHERE w.user_id=:u AND w.kind='gym_workout' AND json_extract(e.value,'$.exercise_id')=:id "
                "AND EXISTS (SELECT 1 FROM json_each(e.value,'$.logged_sets') s "
                "WHERE json_extract(s.value,'$.done')=1 AND (json_extract(s.value,'$.reps') IS NOT NULL "
                "OR json_extract(s.value,'$.seconds') IS NOT NULL)) "
                "ORDER BY json_extract(w.data,'$.started_at') DESC LIMIT 20"
            ),
            {"u": user_id(), "id": exercise_id},
        ).all()
    result = []
    for raw, exercise_raw in rows:
        workout, exercise = json.loads(raw), json.loads(exercise_raw)
        performed = [
            s
            for s in exercise["logged_sets"]
            if s["done"] and (s["reps"] is not None or s.get("seconds") is not None)
        ]
        result.append(
            {
                "workout_id": workout["id"],
                "date": workout["started_at"],
                "sets": performed,
                "finished": bool(workout.get("finished_at")),
            }
        )
    return result


def recent_workouts(limit=50):
    with db.connection() as conn:
        rows = conn.execute(
            text(
                "SELECT data FROM records WHERE user_id=:u AND kind='gym_workout' "
                "ORDER BY json_extract(data,'$.started_at') DESC LIMIT :l"
            ),
            {"u": user_id(), "l": limit},
        ).all()
    return [json.loads(r[0]) for r in rows]


def overview():
    return {
        "programs": [
            {
                k: v
                for k, v in repair_program(r["data"]).items()
                if k not in {"source_sheets", "selection"}
            }
            for r in db.records("gym_program", 30)
        ],
        "exercises": [r["data"] for r in db.records("gym_exercise", 1000)],
        "workouts": [workout_view(w) for w in recent_workouts()],
    }


def start(program_id, day_id):
    with lock:
        program = repair_program(db.record("gym_program", program_id))
        day = next((d for d in program.get("days", []) if d["id"] == day_id), None)
        if (
            not day
            or program.get("archived")
            or day.get("hidden")
            or day["sheet"] in program.get("hidden_sheets", [])
        ):
            raise ValueError("Programme ou séance introuvable ou supprimé.")
        rows = []
        for item in day["exercises"]:
            if item.get("hidden"):
                continue
            past = history(item["exercise_id"])
            reference = past[0] if past else None
            logs = [
                {"weight": None, "reps": None, "seconds": None, "done": False}
                for _ in range(item["sets"] or 1)
            ]
            rows.append(
                {
                    **item,
                    "logged_sets": logs,
                    "reference": reference,
                    "excel_history": imported_history(item["exercise_id"]),
                }
            )
        if not rows:
            raise ValueError("Cette séance ne contient plus d’exercice actif.")
        value = {
            "id": uuid.uuid4().hex,
            "display_version": 2,
            "program_id": program_id,
            "title": day.get("display_name") or day["name"],
            "started_at": db.now(),
            "finished_at": None,
            "revision": 1,
            "exercises": rows,
        }
        db.upsert_record("gym_workout", value["id"], value)
        return value


class LoggedSet(BaseModel):
    weight: float | None = Field(default=None, ge=0, le=2000, allow_inf_nan=False)
    reps: int | None = Field(default=None, ge=0, le=1000)
    seconds: int | None = Field(default=None, ge=0, le=7200)
    done: bool = False


class WorkoutUpdate(BaseModel):
    revision: int = Field(ge=1)
    sets: dict[str, list[LoggedSet]] = Field(max_length=1000)
    finish: bool = False


class Conflict(ValueError):
    pass


def update_workout(key, body):
    with lock:
        value = db.record("gym_workout", key)
        if not value:
            return None
        if value["revision"] != body.revision:
            raise Conflict("Séance modifiée ailleurs. Recharge avant de continuer.")
        if value.get("finished_at"):
            raise Conflict("Séance terminée ; son historique est conservé.")
        if set(body.sets) != {e["id"] for e in value["exercises"]}:
            raise ValueError("Liste des exercices incohérente.")
        for exercise in value["exercises"]:
            sets = body.sets[exercise["id"]]
            if not 1 <= len(sets) <= 30 or any(
                s.done and s.reps is None and s.seconds is None for s in sets
            ):
                raise ValueError(
                    "Renseigne les répétitions des séries validées (30 séries maximum)."
                )
            exercise["logged_sets"] = [s.model_dump() for s in sets]
        value.update(revision=value["revision"] + 1, updated_at=db.now())
        if body.finish:
            if not any(s["done"] for e in value["exercises"] for s in e["logged_sets"]):
                raise ValueError("Valide au moins une série avant de terminer.")
            value["finished_at"] = db.now()
        db.upsert_record("gym_workout", key, value)
        return value


def set_video(key, url):
    with lock:
        value = db.record("gym_exercise", key)
        if not value:
            return None
        value["video_id"] = video_id(url)
        db.upsert_record("gym_exercise", key, value)
        return value


ALIASES.update(
    {
        "comments": ["commentaires de seance", "commentaires"],
        "rm": ["rm"],
        "short_rest": ["repos court"],
        "group": ["groupe", "phase"],
        "order": ["ordre", "order"],
        "tempo": ["tempo"],
        "performance": ["performance", "performances"],
    }
)


def safe_media(url):
    p = urlparse(url or "")
    if p.username or p.password:
        return None
    return (
        url
        if p.scheme == "https"
        and p.hostname
        in {"1drv.ms", "onedrive.live.com", "youtu.be", "youtube.com", "www.youtube.com"}
        else None
    )


def workout_rows(sheet, chosen):
    week, session = "", chosen.name
    structured = "order" in chosen.mapping
    for index, row in enumerate(
        sheet.get("expanded", sheet["rows"])[chosen.header + 1 :], chosen.header + 2
    ):
        name = row[chosen.mapping["name"]].strip()
        marker = next((v for v in row if re.fullmatch(r"semaine\s+\d+", normalized(v))), None)
        if marker and not name:
            week = marker
            continue
        if re.match(r"^seance\s+\d+", normalized(name)):
            session = name
            continue
        if (
            normalized(name).startswith("consignes generales")
            or normalized(name) in ALIASES["name"]
        ):
            continue
        if structured and not row[chosen.mapping["order"]].strip():
            continue
        label = " · ".join(
            v for v in (chosen.name, week, session if session != chosen.name else "") if v
        )
        yield index, row, label, week, session


def imported_history(exercise_id):
    with db.connection() as conn:
        rows = conn.execute(
            text(
                "SELECT data FROM records WHERE user_id=:u AND kind='gym_excel_history' "
                "AND json_extract(data,'$.exercise_id')=:e ORDER BY updated_at DESC, "
                "json_extract(data,'$.row') DESC LIMIT 30"
            ),
            {"u": user_id(), "e": exercise_id},
        ).all()
    return [performance_view(json.loads(r[0])) for r in rows]


def context():
    return [
        {
            "date": w["started_at"],
            "completed": bool(w["finished_at"]),
            "title": w["title"],
            "units": {"weight": "kg", "reps": "count", "seconds": "seconds"},
            "exercises": [
                {"name": e["name"], "sets": [s for s in e["logged_sets"] if s["done"]]}
                for e in w["exercises"][:25]
            ],
        }
        for w in recent_workouts(5)
    ]


class ProgramAction(BaseModel):
    revision: int = Field(ge=1)
    action: str = Field(
        pattern="^(archive|restore_program|hide_sheet|restore_sheet|hide_day|restore_day|hide_exercise|restore_exercise)$"
    )
    sheet: str = Field(default="", max_length=100)
    day_id: str = Field(default="", max_length=100)
    exercise_id: str = Field(default="", max_length=100)


class ProgramRevision(BaseModel):
    revision: int = Field(ge=1)


class ExerciseEdit(BaseModel):
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    sets: int | None = Field(default=None, ge=1, le=20)
    reps: str = Field(default="", max_length=200)
    weight: float | None = Field(default=None, ge=0, le=2000, allow_inf_nan=False)
    rest: str = Field(default="", max_length=200)
    tempo: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=2000)
    illustration: str = Field(
        default="auto",
        pattern="^(auto|generic|squat|lunge|hinge|press|row|pullup|curl|plank|raise)$",
    )


def program_for_edit(key, revision):
    program = db.record("gym_program", key)
    if not program:
        return None
    if program.get("revision", 1) != revision:
        raise Conflict("Programme modifié ailleurs. Recharge avant de continuer.")
    return program


def save_program(program):
    program["revision"] = program.get("revision", 1) + 1
    program["updated_at"] = db.now()
    db.upsert_record("gym_program", program["id"], program)
    return {k: v for k, v in program.items() if k not in {"source_sheets", "selection"}}


def manage_program(key, body):
    with lock:
        program = program_for_edit(key, body.revision)
        if not program:
            return None
        action = body.action
        if action in {"archive", "restore_program"}:
            program["archived"] = action == "archive"
        elif action in {"hide_sheet", "restore_sheet"}:
            if body.sheet not in {d["sheet"] for d in program["days"]}:
                raise ValueError("Feuille introuvable.")
            hidden = set(program.get("hidden_sheets", []))
            if action == "hide_sheet":
                hidden.add(body.sheet)
            else:
                hidden.discard(body.sheet)
            program["hidden_sheets"] = sorted(hidden)
        else:
            day = next((d for d in program["days"] if d["id"] == body.day_id), None)
            if not day:
                raise ValueError("Séance introuvable.")
            if action in {"hide_day", "restore_day"}:
                day["hidden"] = action == "hide_day"
            else:
                item = next((e for e in day["exercises"] if e["id"] == body.exercise_id), None)
                if not item:
                    raise ValueError("Exercice introuvable.")
                item["hidden"] = action == "hide_exercise"
        return save_program(program)


def edit_exercise(key, day_id, item_id, body):
    with lock:
        program = program_for_edit(key, body.revision)
        if not program:
            return None
        item = next(
            (
                e
                for d in program["days"]
                if d["id"] == day_id
                for e in d["exercises"]
                if e["id"] == item_id
            ),
            None,
        )
        if not item:
            raise ValueError("Exercice introuvable.")
        fields = body.model_dump(exclude={"revision"})
        fields["name"] = fields["name"].strip()
        if not fields["name"]:
            raise ValueError("Nom d’exercice requis.")
        changes = {
            k: v
            for k, v in fields.items()
            if v != item.get(k, "auto" if k == "illustration" else "")
        }
        if "sets" in changes:
            changes["sets_label"] = str(fields["sets"]) if fields["sets"] is not None else ""
        if "sets" in changes or "reps" in changes:
            changes["warnings"] = [
                w for w in item.get("warnings", []) if w.split(":", 1)[0] not in changes
            ]
        item.update(changes)
        item["edits"] = {**item.get("edits", {}), **changes}
        return save_program(program)


def reanalyse(key, revision):
    with lock:
        program = program_for_edit(key, revision)
        if not program:
            return None
        source = db.record("gym_source", key)
        if not source:
            raise ValueError("Fichier Excel d’origine introuvable.")
        fresh = preview(source["filename"], source["base64"], refresh=True)
        selection = program.get("selection") or {
            "title": program["title"],
            "performances_are_kg": True,
            "sheets": [
                {k: s[k] for k in ("name", "header", "mapping")}
                for s in program["source_sheets"]
                if s["name"] in {d["sheet"] for d in program["days"]}
            ],
        }
        if fresh["id"] != key:
            raise ValueError("Source de programme incohérente.")
        result = confirm(key, ImportSelection(**selection), rebuild=True)
        return {k: v for k, v in result.items() if k not in {"source_sheets", "selection"}}


class ProgramTitle(BaseModel):
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    sheet: str = Field(default="", max_length=100)
    day_id: str = Field(default="", max_length=100)


def rename_program_item(key, body):
    with lock:
        program = program_for_edit(key, body.revision)
        if not program:
            return None
        title = body.title.strip()
        if not title:
            raise ValueError("Nom requis.")
        if body.sheet and body.day_id:
            raise ValueError("Choisir une feuille ou une séance.")
        if body.sheet:
            if body.sheet not in {d["sheet"] for d in program["days"]}:
                raise ValueError("Feuille introuvable.")
            program.setdefault("sheet_titles", {})[body.sheet] = title
        elif body.day_id:
            day = next((d for d in program["days"] if d["id"] == body.day_id), None)
            if not day:
                raise ValueError("Séance introuvable.")
            day["display_name"] = title
        else:
            if len(title) > 120:
                raise ValueError("120 caractères maximum pour le programme.")
            program["title"] = title
            if program.get("selection"):
                program["selection"]["title"] = title
        return save_program(program)
