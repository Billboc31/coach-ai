"""Explicit, owner-scoped requests for additional Garmin activity measurements."""

import uuid

from coach import activities, activity_series, db

FIELDS = {"all", "laps", *activity_series.CHANNELS}


def cards():
    return sorted(
        [r["data"] for r in db.records("coach_data_request", 1000)],
        key=lambda r: r.get("created_at", ""),
        reverse=True,
    )


def get(key):
    return db.record("coach_data_request", key)


def propose(items, assistant_id, allowed_ids):
    result, seen = [], set()
    for item in items[:3] if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("kind") != "activity_details":
            continue
        key = item.get("activity_id")
        if not isinstance(key, str) or key not in allowed_ids or key in seen:
            continue
        if not key.isascii() or not key.isdecimal() or not 0 < int(key) < 10**20:
            continue
        activity = db.record("activity", key)
        if not activity:
            continue
        fields = item.get("fields", ["all"])
        if (
            not isinstance(fields, list)
            or not fields
            or len(fields) > 12
            or any(not isinstance(f, str) or f not in FIELDS for f in fields)
        ):
            continue
        reason = item.get("reason", "")
        if not isinstance(reason, str):
            reason = ""
        value = {
            "id": uuid.uuid4().hex,
            "kind": "activity_details",
            "activity_id": key,
            "fields": sorted(set(fields)),
            "reason": reason[:240],
            "activity_name": str(activity.get("activityName") or "Séance Garmin")[:100],
            "activity_date": str(activity.get("startTimeLocal") or "")[:10],
            "status": "proposed",
            "chat_message_id": assistant_id,
            "created_at": db.now(),
        }
        db.upsert_record("coach_data_request", value["id"], value)
        result.append(value)
        seen.add(key)
    return result


def load(key):
    value = get(key)
    if not value or not db.record("activity", value["activity_id"]):
        raise LookupError("Demande de données introuvable.")
    detail = activities.details(value["activity_id"])
    # A successful read already cached for this activity needs no additional provider call.
    if not detail.get("fetched_at"):
        detail = activities.refresh(value["activity_id"])
    value.update(status="ready", loaded_at=db.now())
    db.upsert_record("coach_data_request", key, value)
    return value


def detail_context(value):
    detail = activities.details(value["activity_id"])
    if not detail or not detail.get("fetched_at"):
        return None
    fields = value["fields"]
    all_fields = "all" in fields
    data = detail["data"]
    result = {
        "activity_id": value["activity_id"],
        "fetched_at": detail["fetched_at"],
        "requested_fields": fields,
        "summary": {
            k: data.get(k)
            for k in (*activities.METRICS, "activityName", "startTimeLocal", "activityType")
        },
    }
    if all_fields or "laps" in fields:
        laps = detail.get("laps") or []
        result.update(laps=laps[:60], total_laps=len(laps), laps_limit=60)
    series = detail.get("series") or {}
    count = series.get("count", 0)
    indices = (
        sorted(
            {round(i * (count - 1) / max(1, min(count, 180) - 1)) for i in range(min(count, 180))}
        )
        if count
        else []
    )
    axes = series.get("axes") or {}
    channels = []
    for channel in series.get("channels", []):
        if channel.get("key") not in activity_series.CHANNELS:
            continue
        if not all_fields and channel["key"] not in fields:
            continue
        values = channel.get("values") or []
        valid = [n for v in values if (n := activity_series.number(v)) is not None]
        channels.append(
            {
                "key": channel["key"],
                "unit": channel.get("unit"),
                "valid_count": len(valid),
                "min": min(valid) if valid else None,
                "max": max(valid) if valid else None,
                "values": [values[i] if i < len(values) else None for i in indices],
            }
        )
    result["charts"] = {
        "source_sample_count": count,
        "sample_limit": 180,
        "sampling": "regular_indices; extrema computed over all cached samples",
        "axes": {
            name: [vals[i] if i < len(vals) else None for i in indices]
            for name, vals in axes.items()
            if name in {"time", "distance"}
        },
        "channels": channels,
        "status": series.get("status", "no_samples"),
        "unavailable_requested_fields": [
            f for f in fields if f not in {"all", "laps"} and f not in {c["key"] for c in channels}
        ],
    }
    return result


def context(recent_ids=(), selected_id=None):
    if selected_id:
        selected = get(selected_id)
        if not selected or selected.get("status") != "ready":
            raise LookupError("Charge les données de cette demande avant de demander l’analyse.")
        candidates = [selected]
    else:
        candidates = [
            c
            for c in cards()
            if c.get("status") == "ready" and c.get("chat_message_id") in recent_ids
        ][:1]
    return [detail for c in candidates if (detail := detail_context(c)) is not None]
