"""Owner-scoped activity browsing and on-demand Garmin summaries/splits."""

import json

from sqlalchemy import text

from coach import db
from coach.config import user_id
from coach.garmin import Garmin, session_path
from coach.garmin_lock import storage_lock

SPORTS = {
    "running": ("running",),
    "cycling": ("cycling", "biking"),
    "strength": ("strength", "fitness_equipment"),
    "tennis": ("tennis",),
    "swimming": ("swimming",),
    "walking": ("walking", "hiking"),
}
METRICS = (
    "duration",
    "movingDuration",
    "distance",
    "averageHR",
    "maxHR",
    "calories",
    "elevationGain",
    "elevationLoss",
    "averageSpeed",
    "maxSpeed",
    "averagePower",
    "maxPower",
    "aerobicTrainingEffect",
    "anaerobicTrainingEffect",
    "averageRunningCadenceInStepsPerMinute",
    "averageBikeCadence",
)


def browse(offset=0, sport="", query="", start=None, end=None):
    clause = "user_id=:u AND kind='activity'"
    params = {"u": user_id(), "offset": offset, "query": query.lower()}
    if query:
        clause += " AND instr(lower(COALESCE(json_extract(data,'$.activityName'),'')),:query)>0"
    if sport:
        terms = SPORTS.get(sport)
        if not terms:
            raise ValueError("Sport inconnu.")
        conditions = []
        for i, term in enumerate(terms):
            conditions.append(f"instr(lower(json_extract(data,'$.activityType.typeKey')), :s{i})>0")
            params[f"s{i}"] = term
        clause += " AND (" + " OR ".join(conditions) + ")"
    stamp = "COALESCE(json_extract(data,'$.startTimeLocal'),json_extract(data,'$.startTimeGMT'),'')"
    if start:
        clause += f" AND substr({stamp},1,10)>=:start"
        params["start"] = start.isoformat()
    if end:
        clause += f" AND substr({stamp},1,10)<=:end"
        params["end"] = end.isoformat()
    with db.connection() as conn:
        rows = conn.execute(
            text(
                f"SELECT record_key,data,updated_at FROM records WHERE {clause} "
                f"ORDER BY {stamp} DESC,record_key DESC LIMIT 24 OFFSET :offset"
            ),
            params,
        ).all()
        totals = (
            conn.execute(
                text(
                    f"SELECT COUNT(*) AS count, SUM(json_extract(data,'$.duration')) "
                    f"AS duration, SUM(json_extract(data,'$.distance')) AS distance "
                    f"FROM records WHERE {clause}"
                ),
                params,
            )
            .mappings()
            .one()
        )
    return {
        "items": [{"key": r[0], "data": json.loads(r[1]), "updated_at": r[2]} for r in rows],
        "total": totals["count"],
        "totals": dict(totals),
        "page_size": 24,
    }


def details(key):
    activity = db.record("activity", key)
    if not activity:
        return None
    cached = db.record("activity_detail", key)
    return {
        "key": key,
        "data": {**activity, **cached.get("summary", {})},
        "laps": cached.get("laps", []),
        "fetched_at": cached.get("fetched_at"),
    }


class DetailUnavailable(ValueError):
    pass


def refresh(key):
    with storage_lock():
        client = Garmin()
        client.login(session_path())
        raw = client.get_activity(key)
        splits = client.get_activity_splits(key)
        if not isinstance(raw, dict) or not isinstance(raw.get("summaryDTO"), dict):
            raise DetailUnavailable("Détails Garmin indisponibles pour cette activité.")
        summary = {k: raw["summaryDTO"][k] for k in METRICS if k in raw["summaryDTO"]}
        laps = []
        for lap in (splits.get("lapDTOs", []) if isinstance(splits, dict) else [])[:500]:
            if isinstance(lap, dict):
                laps.append({k: lap[k] for k in (*METRICS, "lapIndex") if k in lap})
        # Save only after both reads succeed: a failed refresh preserves the previous cache.
        db.upsert_record(
            "activity_detail", key, {"summary": summary, "laps": laps, "fetched_at": db.now()}
        )
    return details(key)
