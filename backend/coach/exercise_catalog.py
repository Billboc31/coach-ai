"""Versioned public exercise catalogue and owner-scoped alias decisions.

Catalogue facts and licence provenance are bundled; private names never leave the app.
User exercise IDs and recorded sets are never rewritten when changing a correspondence.
"""

import json
import re
import threading
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from importlib.resources import files

from pydantic import BaseModel, Field
from sqlalchemy import text

from coach import db
from coach.config import user_id

lock = threading.RLock()
CONVENTIONS = {"unspecified", "total", "per_dumbbell", "added", "machine", "bodyweight"}
# Curated public synonyms. A machine, grip, side or incline remains a separate catalogue ID.
ALIASES = {
    73: (
        "Développé couché à la barre",
        ["DC barre", "développé couché barre", "barbell bench press"],
    ),
    75: ("Développé couché aux haltères", ["DC haltères", "DC haltere", "bench press dumbbells"]),
    76: ("Développé couché prise serrée", ["DC barre prise serrée", "close grip bench press"]),
    81: (
        "Rowing haltère à un bras",
        [
            "rowing haltère un bras",
            "rowing haltere 1 bras",
            "tirage bûcheron",
            "dumbbell row single arm",
        ],
    ),
    83: ("Rowing barre en pronation", ["rowing barre pronation", "barbell bent over row"]),
    84: ("Rowing barre en supination", ["rowing barre supination", "reverse grip barbell row"]),
    91: ("Curl biceps à la barre", ["curl barre", "barbell curl"]),
    92: ("Curl biceps aux haltères", ["curl haltères", "dumbbell curl"]),
    94: ("Curl biceps à la barre EZ", ["curl EZ", "curl barre EZ"]),
    95: ("Curl biceps à la poulie", ["curl poulie", "cable biceps curl"]),
    152: (
        "Tractions en supination",
        ["traction supination", "tractions supination", "chin up", "chin ups"],
    ),
    184: (
        "Soulevé de terre à la barre",
        ["soulevé de terre barre", "SDT barre", "barbell deadlift"],
    ),
    185: ("Développé décliné à la barre", ["DC décliné barre", "développé décliné barre"]),
    186: ("Développé décliné aux haltères", ["DC décliné haltères", "développé décliné haltères"]),
    203: ("Squat goblet avec haltère", ["goblet squat haltère", "squat goblet haltère"]),
    204: ("Curl incliné aux haltères", ["curl incliné haltères", "incline dumbbell curl"]),
    205: (
        "Fentes statiques aux haltères",
        ["fentes haltères statiques", "dumbbell stationary lunge"],
    ),
    206: ("Fentes marchées aux haltères", ["fentes marchées haltères", "walking dumbbell lunge"]),
    222: ("Face pull à la poulie", ["face pull poulie", "facepull poulie"]),
    237: ("Écartés à la poulie", ["écarté poulie", "cable fly"]),
    238: ("Écartés couchés aux haltères", ["écarté couché haltères", "dumbbell chest fly"]),
    257: ("Squat avant à la barre", ["front squat barre", "squat avant barre"]),
    272: ("Curl marteau aux haltères", ["curl marteau haltères", "dumbbell hammer curl"]),
    294: ("Hip thrust à la barre", ["hip thrust barre", "barbell hip thrust"]),
    348: (
        "Élévations latérales aux haltères",
        ["élévation latérale haltères", "élévations latérales haltères", "dumbbell lateral raise"],
    ),
    365: ("Leg curl couché", ["leg curl allongé", "lying leg curl"]),
    366: ("Leg curl assis", ["seated leg curl"]),
    369: ("Leg extension", ["extension quadriceps machine", "leg extensions"]),
    371: ("Presse à cuisses", ["presse à cuisse", "leg press"]),
    458: (
        "Gainage ventral sur les avant-bras",
        ["gainage ventral avant bras", "planche avant bras", "forearm plank"],
    ),
    475: (
        "Tractions en pronation",
        ["tractions pronation", "traction pronation", "overhand pull up"],
    ),
    507: (
        "Soulevé de terre roumain à la barre",
        ["SDT roumain barre", "RDL barre", "barbell romanian deadlift"],
    ),
    537: ("Développé incliné aux haltères", ["DC incliné haltères", "développé incliné haltères"]),
    538: ("Développé incliné à la barre", ["DC incliné barre", "développé incliné barre"]),
    566: ("Développé épaules à la barre", ["développé militaire barre", "overhead barbell press"]),
    567: (
        "Développé épaules aux haltères",
        ["développé militaire haltères", "dumbbell shoulder press"],
    ),
    580: ("Gainage latéral", ["planche latérale", "side plank"]),
    615: ("Squat arrière à la barre", ["squat barre", "back squat barre", "barbell back squat"]),
    622: ("Mollets debout", ["standing calf raise"]),
    805: ("Extension triceps à la poulie", ["triceps poulie", "tricep cable pushdown"]),
    1117: ("Tirage horizontal assis à la poulie", ["seated cable row", "tirage assis poulie"]),
    1312: ("Squat au poids du corps", ["air squat", "squat poids du corps", "bodyweight squat"]),
    1706: (
        "Squat bulgare aux haltères",
        ["squat bulgare haltères", "fente bulgare haltères", "bulgarian split squat dumbbells"],
    ),
}
AMBIGUOUS = {
    "dc",
    "squat",
    "rowing",
    "curl",
    "curl biceps",
    "developpe couche",
    "bench press",
    "tractions",
    "pull ups",
    "gainage",
    "leg curl",
    "fentes",
    "hip thrust",
    "souleve de terre",
    "romanian deadlift",
}


def normalized(value):
    value = unicodedata.normalize("NFKD", str(value).lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


@lru_cache(maxsize=1)
def catalogue():
    directory = files("coach").joinpath("data/exercise_catalog")
    result = {}
    for path in sorted(directory.iterdir(), key=lambda p: p.name):
        if not path.name.startswith("catalog-"):
            continue
        for entry in json.loads(path.read_text()):
            label, aliases = ALIASES.get(entry["source_id"], (entry["name"], []))
            result[entry["id"]] = {
                **entry,
                "name": label,
                "aliases": list(dict.fromkeys([entry["name"], *entry["aliases"], label, *aliases])),
            }
    return result


def manifest():
    return json.loads(files("coach").joinpath("data/exercise_catalog/manifest.json").read_text())


@lru_cache(maxsize=1)
def exact_index():
    result = {}
    for entry in catalogue().values():
        for alias in entry["aliases"]:
            result.setdefault(normalized(alias), set()).add(entry["id"])
    # Explicit curated synonyms establish one preferred public record for equivalent wording.
    for source_id, (name, aliases) in ALIASES.items():
        key = f"wger:{source_id}"
        if key in catalogue():
            for alias in [name, *aliases]:
                result[normalized(alias)] = {key}
    return result


def exact(name):
    key = normalized(name)
    candidates = exact_index().get(key, set())
    return next(iter(candidates)) if key not in AMBIGUOUS and len(candidates) == 1 else None


def search(query="", *, limit=12, offset=0, category="", equipment=""):
    query = normalized(query)
    tokens = set(query.split())
    scored = []
    for entry in catalogue().values():
        if category and entry["category"] != category:
            continue
        if equipment and equipment not in entry["equipment"]:
            continue
        aliases = [normalized(a) for a in entry["aliases"]]
        if not query:
            score = 1
        elif query in aliases:
            score = 1
        else:
            score = max(
                (0.8 if query in a else 0)
                + 0.15 * len(tokens & set(a.split())) / max(len(tokens), 1)
                for a in aliases
            )
            score = max(score, max(SequenceMatcher(None, query, a).ratio() * 0.6 for a in aliases))
        if query and score < 0.28:
            continue
        scored.append((score, entry))
    scored.sort(key=lambda p: (-p[0], normalized(p[1]["name"]), p[1]["id"]))
    return {
        "items": [{**e, "score": round(s, 3)} for s, e in scored[offset : offset + limit]],
        "total": len(scored),
        "catalogue": manifest(),
        "categories": sorted({e["category"] for e in catalogue().values()}),
        "equipment": sorted({v for e in catalogue().values() for v in e["equipment"]}),
    }


def binding(exercise_id, *, name=None):
    record = db.record("gym_binding", exercise_id)
    if record:
        return record
    exercise = db.record("gym_exercise", exercise_id)
    name = name or exercise.get("name", "")
    key = exact(name) if name else None
    return {
        "exercise_id": exercise_id,
        "catalog_id": key,
        "weight_convention": "unspecified",
        "weight_context": "",
        "revision": 0,
        "method": "exact" if key else "unresolved",
    }


def resolution(exercise_id, *, name=None):
    value = binding(exercise_id, name=name)
    exercise = db.record("gym_exercise", exercise_id)
    return {
        **value,
        "entry": catalogue().get(value["catalog_id"]),
        "source_name": name or exercise.get("name", ""),
    }


def decisions():
    return {r["key"]: r["data"] for r in db.records("gym_binding", 10000)}


def decorate(item, snapshot=None):
    if snapshot is None:
        resolved = resolution(item["exercise_id"], name=item["name"])
    else:
        key = exact(item["name"])
        resolved = snapshot.get(
            item["exercise_id"],
            {
                "catalog_id": key,
                "weight_convention": "unspecified",
                "method": "exact" if key else "unresolved",
            },
        )
    entry = catalogue().get(resolved["catalog_id"])
    return {
        **item,
        "recorded_weight_convention": item.get("weight_convention"),
        "recorded_weight_context": item.get("weight_context"),
        "recorded_catalog_id": item.get("catalog_id"),
        "recorded_canonical_name": item.get("canonical_name"),
        "canonical_name": entry["name"] if entry else None,
        "catalog_id": resolved["catalog_id"],
        "weight_convention": resolved["weight_convention"],
        "weight_context": resolved.get("weight_context", ""),
        "catalogue_status": resolved["method"],
    }


class BindingUpdate(BaseModel):
    weight_context: str = Field(default="", max_length=100)
    revision: int = Field(ge=0)
    catalog_id: str | None = Field(default=None, max_length=80)
    weight_convention: str = Field(
        default="unspecified", pattern="^(unspecified|total|per_dumbbell|added|machine|bodyweight)$"
    )


class BindingConflict(ValueError):
    pass


def set_binding(exercise_id, body):
    with lock:
        if not db.record("gym_exercise", exercise_id):
            return None
        old = binding(exercise_id)
        if old["revision"] != body.revision:
            raise BindingConflict("Correspondance modifiée ailleurs. Recharge la fiche.")
        if body.catalog_id is not None and body.catalog_id not in catalogue():
            raise ValueError("Exercice du catalogue introuvable.")
        value = {
            "exercise_id": exercise_id,
            "catalog_id": body.catalog_id,
            "weight_convention": body.weight_convention,
            "weight_context": body.weight_context.strip(),
            "revision": old["revision"] + 1,
            "method": "confirmed" if body.catalog_id else "unresolved",
            "updated_at": db.now(),
        }
        db.upsert_record("gym_binding", exercise_id, value)
        return resolution(exercise_id)


def compatible_ids(exercise_id):
    """Only confirmed compatible charge conventions pool distinct private aliases."""
    current = binding(exercise_id)
    if (
        not current["catalog_id"]
        or current["weight_convention"] == "unspecified"
        or (current["weight_convention"] == "machine" and not current.get("weight_context"))
    ):
        return [exercise_id]
    with db.connection() as conn:
        rows = conn.execute(
            text(
                "SELECT record_key FROM records WHERE user_id=:u AND kind='gym_binding' AND json_extract(data,'$.catalog_id')=:c AND json_extract(data,'$.weight_convention')=:w AND COALESCE(json_extract(data,'$.weight_context'),'')=:context"
            ),
            {
                "u": user_id(),
                "c": current["catalog_id"],
                "w": current["weight_convention"],
                "context": current.get("weight_context", ""),
            },
        ).all()
    return sorted({exercise_id, *(r[0] for r in rows)})
