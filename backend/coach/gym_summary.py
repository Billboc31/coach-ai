"""Owner-scoped weekly strength review of recorded sets and imported Garmin activities."""

import json
import math
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field
from sqlalchemy import text

from coach import db, exercise_catalog
from coach.config import user_id
from coach.owner_resources import OwnerLock

lock = OwnerLock()


def local_zone():
    try:
        return ZoneInfo(db.profile().get("timezone") or "Europe/Paris")
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return ZoneInfo("Europe/Paris")


def stamp(value, zone):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed.astimezone(zone)
    except (ValueError, TypeError):
        return None


def number(value):
    return (
        value
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
        else None
    )


def stored(kind):
    # No overview pagination: a complete week must not be truncated at 24 or 50 records.
    with db.connection() as conn:
        rows = conn.execute(
            text("SELECT record_key,data FROM records WHERE user_id=:u AND kind=:k"),
            {"u": user_id(), "k": kind},
        ).all()
    return {key: json.loads(raw) for key, raw in rows}


def strength(activity):
    sport = str(activity.get("activityType", {}).get("typeKey", "")).lower()
    return "strength" in sport or "fitness_equipment" in sport


def activity_time(activity, zone):
    # Garmin GMT fields are UTC even when the string lacks a timezone suffix.
    utc = stamp(activity.get("startTimeGMT"), timezone.utc)
    return utc.astimezone(zone) if utc else stamp(activity.get("startTimeLocal"), zone)


def performed(exercise):
    return [
        {
            "weight": number(s.get("weight")),
            "reps": number(s.get("reps")),
            "seconds": number(s.get("seconds")),
        }
        for s in exercise.get("logged_sets", [])
        if s.get("done") is True
        and (number(s.get("reps")) is not None or number(s.get("seconds")) is not None)
    ]


def identity(exercise):
    # Never combine machines, weight conventions or previously recorded variants.
    return (
        exercise.get("exercise_id") or exercise.get("id"),
        exercise_catalog.current_id(exercise.get("catalog_id")),
        exercise.get("weight_convention") or "unspecified",
        exercise.get("weight_context") or "",
    )


def garmin_view(key, activity, zone):
    started = activity_time(activity, zone)
    return {
        "id": key,
        "title": activity.get("activityName") or "Musculation Garmin",
        "started_at": started.isoformat() if started else None,
        "duration_seconds": number(activity.get("duration")),
        "average_hr": number(activity.get("averageHR")),
        "max_hr": number(activity.get("maxHR")),
        "calories": number(activity.get("calories")),
    }


def associations(workouts, activities, links, zone):
    linked, used = {}, set()
    # Explicit decisions always take precedence over time-based suggestions.
    for wid, decision in links.items():
        aid = decision.get("activity_id")
        if (
            wid in workouts
            and aid in activities
            and aid not in used
            and any(performed(e) for e in workouts[wid].get("exercises", []))
        ):
            linked[wid] = (aid, "manual")
            used.add(aid)
    candidates = {}
    for wid, workout in workouts.items():
        if (
            wid in links
            or wid in linked
            or not any(performed(e) for e in workout.get("exercises", []))
        ):
            continue
        start = stamp(workout.get("started_at"), zone)
        candidates[wid] = [
            aid
            for aid, activity in activities.items()
            if aid not in used
            and start
            and (other := activity_time(activity, zone))
            and abs(start.timestamp() - other.timestamp()) <= 90 * 60
        ]
    counts = Counter(aid for choices in candidates.values() for aid in choices)
    for wid, choices in candidates.items():
        if len(choices) == 1 and counts[choices[0]] == 1:
            linked[wid] = (choices[0], "automatic")
    return linked


class GarminLink(BaseModel):
    # Null explicitly keeps the workout separate; it does not silently re-enable matching.
    activity_id: str | None = Field(default=None, max_length=100)
    automatic: bool = False


def set_link(workout_id, body):
    with lock.current():
        workout = db.record("gym_workout", workout_id)
        if not workout:
            return None
        if body.automatic:
            db.delete_record("gym_garmin_link", workout_id)
            return {"saved": True}
        if body.activity_id is not None:
            activity = db.record("activity", body.activity_id)
            if not activity or not strength(activity):
                raise ValueError("Activité de musculation introuvable dans ton compte.")
            existing_workouts = stored("gym_workout")
            if any(
                key != workout_id
                and key in existing_workouts
                and value.get("activity_id") == body.activity_id
                for key, value in stored("gym_garmin_link").items()
            ):
                raise ValueError("Cette activité est déjà associée à une autre séance.")
        db.upsert_record("gym_garmin_link", workout_id, {"activity_id": body.activity_id})
        return {"saved": True}


def weekly(day: date | None = None):
    zone = local_zone()
    day = day or datetime.now(zone).date()
    monday = day - timedelta(days=day.weekday())
    begin = datetime.combine(monday, time.min, zone)
    end = datetime.combine(monday + timedelta(days=7), time.min, zone)
    workouts = stored("gym_workout")
    activities = {key: value for key, value in stored("activity").items() if strength(value)}
    links = stored("gym_garmin_link")
    matches = associations(workouts, activities, links, zone)
    selected = sorted(
        (
            w
            for w in workouts.values()
            if (start := stamp(w.get("started_at"), zone))
            and begin <= start < end
            and any(performed(e) for e in w.get("exercises", []))
        ),
        key=lambda w: w["started_at"],
        reverse=True,
    )
    catalogue = exercise_catalog.catalogue()
    previous = {}
    for w in workouts.values():
        start = stamp(w.get("started_at"), zone)
        if not start or start >= begin:
            continue
        for e in w.get("exercises", []):
            for s in performed(e):
                if s["weight"] is not None and s["reps"]:
                    key = (identity(e), s["reps"])
                    old = previous.get(key)
                    if not old or start > old["stamp"]:
                        previous[key] = {
                            "stamp": start,
                            "weight": s["weight"],
                            "record": s["weight"],
                        }
                    elif start == old["stamp"]:
                        old["weight"] = max(old["weight"], s["weight"])
                    previous[key]["record"] = max(
                        previous[key]["record"], s["weight"], old["record"] if old else 0
                    )
    primary, secondary = Counter(), Counter()
    sessions, exercises = [], {}
    total_sets = unknown_muscle_sets = unknown_load_sets = 0
    volume = 0
    for workout in selected:
        workout_exercises = []
        for e in workout.get("exercises", []):
            sets = performed(e)
            if not sets:
                continue
            key = identity(e)
            # Use the recorded variant. A later catalogue edit must not rewrite history.
            catalog_id = key[1]
            if not catalog_id:
                catalog_id = exercise_catalog.resolution(
                    e.get("exercise_id", ""), name=e.get("name", "")
                )["catalog_id"]
            entry = catalogue.get(catalog_id) or {}
            main = sorted(set(entry.get("muscles", [])))
            support = sorted(set(entry.get("muscles_secondary", [])) - set(main))
            primary.update({m: len(sets) for m in main})
            secondary.update({m: len(sets) for m in support})
            total_sets += len(sets)
            if not main:
                unknown_muscle_sets += len(sets)
            known = [s for s in sets if s["weight"] is not None and s["reps"] is not None]
            unknown_load_sets += len(sets) - len(known)
            item_volume = sum(s["weight"] * s["reps"] for s in known)
            volume += item_volume
            item = exercises.setdefault(
                key,
                {
                    "id": e.get("exercise_id") or e["id"],
                    "name": e.get("canonical_name") or entry.get("name") or e["name"],
                    "weight_convention": key[2],
                    "weight_context": key[3],
                    "primary_muscles": main,
                    "secondary_muscles": support,
                    "sets": [],
                    "volume_kg": None,
                },
            )
            item["sets"].extend(
                {**s, "workout_id": workout["id"], "date": workout["started_at"]} for s in sets
            )
            if known:
                item["volume_kg"] = (item["volume_kg"] or 0) + item_volume
            workout_exercises.append({"name": item["name"], "sets": sets})
        match = matches.get(workout["id"])
        activity = garmin_view(match[0], activities[match[0]], zone) if match else None
        finished = stamp(workout.get("finished_at"), zone)
        started = stamp(workout["started_at"], zone)
        elapsed = finished.timestamp() - started.timestamp() if finished and started else None
        sessions.append(
            {
                "id": workout["id"],
                "title": workout.get("title") or "Séance musculation",
                "started_at": started.isoformat(),
                "finished": bool(finished),
                "exercises": workout_exercises,
                "garmin": activity,
                "match_method": match[1]
                if match
                else ("separate" if workout["id"] in links else None),
                "duration_seconds": activity["duration_seconds"]
                if activity
                else (elapsed if elapsed is not None and 0 <= elapsed <= 43200 else None),
            }
        )
    for key, item in exercises.items():
        by_reps = {}
        for s in item["sets"]:
            if s["weight"] is not None and s["reps"]:
                by_reps[s["reps"]] = max(by_reps.get(s["reps"], 0), s["weight"])
        item["progression"] = []
        for reps, weight in sorted(by_reps.items()):
            prior = previous.get((key, reps))
            item["progression"].append(
                {
                    "reps": reps,
                    "weight": weight,
                    "previous_weight": prior["weight"] if prior else None,
                    "previous_date": prior["stamp"].isoformat() if prior else None,
                    "delta_kg": round(weight - prior["weight"], 3) if prior else None,
                    "record": bool(prior and weight > prior["record"]),
                }
            )
    used = {aid for aid, _ in matches.values()}
    unmatched = [
        garmin_view(key, a, zone)
        for key, a in activities.items()
        if key not in used and (start := activity_time(a, zone)) and begin <= start < end
    ]
    durations = [s["duration_seconds"] for s in sessions] + [
        a["duration_seconds"] for a in unmatched
    ]
    muscles = [
        {"name": m, "primary_sets": primary[m], "secondary_sets": secondary[m]}
        for m in sorted(
            primary.keys() | secondary.keys(), key=lambda m: (-primary[m], -secondary[m], m)
        )
    ]
    insights = [
        f"{total_sets} séries validées dans l’app cette semaine. Les séries prévues ou non cochées sont exclues."
    ]
    if primary:
        insights.append(
            "La répartition par muscle compte les séries où il est documenté comme cible principale, séparément des sollicitations secondaires."
        )
    improvements = sum(
        p["delta_kg"] is not None and p["delta_kg"] > 0
        for e in exercises.values()
        for p in e["progression"]
    )
    if improvements:
        insights.append(
            f"{improvements} repère(s) de charge en hausse à répétitions identiques par rapport à la dernière séance comparable avant cette semaine."
        )
    if unknown_muscle_sets:
        insights.append(
            f"{unknown_muscle_sets} séries ont des muscles à identifier : la répartition est partielle."
        )
    if unmatched:
        insights.append(
            f"{len(unmatched)} activité(s) Garmin sans détail d’exercices associé. Associe-les à une séance si elles correspondent."
        )
    if unknown_load_sets:
        insights.append(
            f"{unknown_load_sets} séries sans couple charge/répétitions complet ne contribuent pas au volume."
        )
    if any(not s["finished"] for s in sessions):
        insights.append(
            "Des séances sont encore en cours : leurs séries déjà validées sont incluses."
        )
    return {
        "week_start": monday.isoformat(),
        "week_end": (monday + timedelta(days=6)).isoformat(),
        "timezone": str(zone),
        "totals": {
            "sessions": len(sessions) + len(unmatched),
            "app_sessions": len(sessions),
            "linked_sessions": sum(s["garmin"] is not None for s in sessions),
            "sets": total_sets,
            "volume_kg": round(volume, 3) if total_sets > unknown_load_sets else None,
            "unknown_load_sets": unknown_load_sets,
            "unknown_muscle_sets": unknown_muscle_sets,
            "duration_seconds": sum(d for d in durations if d is not None)
            if any(d is not None for d in durations)
            else None,
            "missing_duration_sessions": sum(d is None for d in durations),
        },
        "muscles": muscles,
        "exercises": sorted(exercises.values(), key=lambda e: e["name"]),
        "sessions": sessions,
        "unmatched_garmin": unmatched,
        "garmin_choices": [
            garmin_view(key, a, zone)
            for key, a in activities.items()
            if (start := activity_time(a, zone))
            and begin - timedelta(days=1) <= start < end + timedelta(days=1)
        ],
        "insights": insights,
    }
