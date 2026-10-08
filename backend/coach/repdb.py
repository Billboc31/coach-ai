"""Fetch licensed in-app data at build time, never redistribute a dataset in git."""

import json
import re
from importlib.resources import files
from urllib.request import urlopen

REVISION = "a360f87f9064de42a9c90228cfebae941a5016d5"
ROOT = f"https://raw.githubusercontent.com/RepDB/exercise-dataset/{REVISION}/"
CREDIT = {
    "name": "RepDB Free Tier v1.0",
    "url": ROOT + "LICENSE-DATA.md",
    "authors": ["RepDB"],
}
# Reviewed names, preserving material, angle and side. Other names stay in English.
NAMES = {
    "leg-press": ("Presse oblique", ["presse à cuisses oblique", "presse inclinée"]),
    "horizontal-leg-press": ("Presse à cuisses horizontale", ["presse horizontale"]),
    "ab-wheel-rollout": ("Roue abdominale", ["ab wheel", "roulette abdos"]),
    "cable-crunch": ("Crunch à la poulie", ["crunch poulie", "abdos poulie"]),
    "bicycle-crunch": ("Crunch bicyclette", ["abdos bicyclette"]),
    "bird-dog": ("Bird dog", ["bird dog"]),
    "box-jump": ("Saut sur box", ["box jump"]),
    "bodyweight-squat": ("Squat au poids du corps", ["squat poids du corps"]),
    "cable-pallof-press": ("Pallof press à la poulie", ["pallof press poulie"]),
    "back-extension": ("Extension du dos", ["extension dos"]),
}
MUSCLES = {
    "rectus_abdominis": "Abs",
    "transverse_abdominis": "Abs",
    "quadriceps": "Quads",
    "gluteus_maximus": "Glutes",
    "gluteus_medius": "Glutes",
    "hamstrings": "Hamstrings",
    "pectoralis_major": "Chest",
    "anterior_deltoid": "Shoulders",
    "lateral_deltoid": "Shoulders",
    "posterior_deltoid": "Shoulders",
    "biceps_brachii": "Biceps",
    "triceps_brachii": "Triceps",
    "brachialis": "Brachialis",
    "gastrocnemius": "Calves",
    "soleus": "Soleus",
    "latissimus_dorsi": "Lats",
    "obliques": "Obliquus externus abdominis",
    "trapezius": "Trapezius",
    "serratus_anterior": "Serratus anterior",
}
CATEGORIES = {
    "core": "Abs",
    "upper_legs": "Legs",
    "lower_legs": "Calves",
    "chest": "Chest",
    "back": "Back",
    "shoulders": "Shoulders",
    "upper_arms": "Arms",
    "forearms": "Arms",
}


def convert(data):
    result = []
    for e in data["exercises"]:
        slug = e["id"]
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            raise ValueError("Invalid RepDB exercise ID")
        name, aliases = NAMES.get(slug, (e["name_en"], []))
        media = []
        for path in dict.fromkeys(e.get("images", {}).get("flat", {}).values()):
            if not re.fullmatch(r"images/flat/[a-z0-9-]+\.webp", path):
                raise ValueError("Invalid RepDB image path")
            media.append({"kind": "image", "url": ROOT + path, "credit": CREDIT})

        def groups(key):
            return list(dict.fromkeys(MUSCLES.get(m, m.replace("_", " ")) for m in e.get(key, [])))

        result.append(
            {
                "id": "repdb:" + slug,
                "source_id": slug,
                "provider": "RepDB",
                "name": name,
                "name_en": e["name_en"],
                "aliases": list(dict.fromkeys([name, e["name_en"], *aliases])),
                "category": CATEGORIES.get(e.get("body_part"), e.get("category", "strength")),
                "equipment": [e["equipment"].replace("_", " ")] if e.get("equipment") else [],
                "muscles": groups("primary_muscles"),
                "muscles_secondary": groups("secondary_muscles"),
                "description": "\n".join(e.get("instructions_en", []))[:1600],
                "description_language": "en",
                "credit": CREDIT,
                "text_credit": CREDIT,
                "source_url": "https://exercise-dataset.com/",
                "media": media,
            }
        )
    return result


def main():
    with urlopen(ROOT + "exercises.json", timeout=60) as response:
        raw = response.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError("RepDB dataset too large")
    entries = convert(json.loads(raw))
    if len(entries) != 609:
        raise ValueError("Unexpected pinned RepDB snapshot")
    path = files("coach").joinpath("data/exercise_catalog/repdb-generated.json")
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    print(f"RepDB: {len(entries)} exercises installed for in-app use")


if __name__ == "__main__":
    main()
