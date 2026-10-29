"""Resolve warm-up ramps within a single session, preserving the source wording."""

import hashlib
import re

from coach import exercise_catalog


def is_ramp(name):
    return bool(re.match(r"^gamme montante(?:\s|$)", exercise_catalog.normalized(name)))


def resolve(items):
    """Return independent rows; never change actual weights, reps or logged set identities."""
    result = [dict(item) for item in items]
    for index, item in enumerate(result):
        original = item.get("source_name", item["name"])
        if "name" in item.get("edits", {}):
            for key in ("is_warmup", "warmup_for_id", "warmup_target_name"):
                item.pop(key, None)
            continue
        if not is_ramp(original):
            continue
        item.update(source_name=original, is_warmup=True)
        target = result[index + 1] if index + 1 < len(result) else None
        if (
            not target
            or target.get("hidden")
            or is_ramp(target.get("source_name", target["name"]))
            or re.search(r"\bfiche[s]?\b", exercise_catalog.normalized(target["name"]))
        ):
            item.update(warmup_for_id=None, warmup_target_name=None)
            continue
        movement = exercise_catalog.coaching(target["name"])[0]
        identity = "warmup:" + target["exercise_id"] + ":" + exercise_catalog.normalized(movement)
        item.update(
            name="Gamme montante " + movement,
            source_exercise_id=item.get("source_exercise_id", item["exercise_id"]),
            exercise_id=hashlib.sha256(identity.encode()).hexdigest()[:24],
            warmup_for_id=target["id"],
            warmup_target_name=movement,
        )
    return result
