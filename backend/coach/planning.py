"""Dated workout plans, explicit confirmations and links to imported activities."""

import json
import threading
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from coach import db
from coach.config import user_id

lock = threading.Lock()
SPORTS = {"running", "cycling", "strength", "tennis", "swimming", "walking", "recovery", "other"}


class Session(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    sport: str
    day: date
    time: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    instructions: str = Field(default="", max_length=2000)
    status: str = "planned"
    activity_id: str | None = Field(default=None, max_length=40)
    revision: int | None = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def title_valid(cls, v):
        if not v.strip():
            raise ValueError("Titre vide")
        return v.strip()

    @field_validator("sport")
    @classmethod
    def sport_valid(cls, v):
        if v not in SPORTS:
            raise ValueError("Sport inconnu")
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v):
        if v not in {"proposed", "planned", "completed", "cancelled", "dismissed"}:
            raise ValueError("Statut inconnu")
        return v

    @field_validator("day")
    @classmethod
    def day_valid(cls, v):
        if not date(1990, 1, 1) <= v <= date.today() + timedelta(days=730):
            raise ValueError("Date hors limites")
        return v

    @field_validator("time")
    @classmethod
    def time_valid(cls, v):
        if v is not None:
            try:
                if datetime.strptime(v, "%H:%M").strftime("%H:%M") != v:
                    raise ValueError()
            except ValueError:
                raise ValueError("Heure HH:MM attendue") from None
        return v


def get(key):
    return db.record("planned_session", key)


def cards():
    return [
        {k: v for k, v in r["data"].items() if k != "history"}
        for r in db.records("planned_session", 1000)
        if r["data"].get("chat_message_id")
    ]


def create(body, *, source="user", message_id=None):
    with lock:
        value = body.model_dump(mode="json", exclude={"revision"})
        if source == "user" and body.status == "proposed":
            value["status"] = "planned"
        if value["activity_id"]:
            validate_link(value["activity_id"], None)
            if body.status != "completed":
                raise ValueError("Une activité liée exige le statut réalisée.")
        value.update(
            id=uuid.uuid4().hex,
            revision=1,
            source=source,
            chat_message_id=message_id,
            created_at=db.now(),
            updated_at=db.now(),
            history=[],
        )
        db.upsert_record("planned_session", value["id"], value)
        return value


def validate_link(activity_id, key):
    if not db.record("activity", activity_id):
        raise ValueError("Activité Garmin introuvable.")
    with db.connection() as conn:
        existing = conn.execute(
            text(
                "SELECT record_key FROM records WHERE user_id=:u "
                "AND kind='planned_session' AND json_extract(data,'$.activity_id')=:a "
                "AND json_extract(data,'$.status')='completed'"
            ),
            {"u": user_id(), "a": activity_id},
        ).all()
    if any(row[0] != key for row in existing):
        raise ValueError("Cette activité est déjà liée à une séance.")


class Conflict(ValueError):
    pass


def update(key, body):
    with lock:
        previous = get(key)
        if not previous:
            return None
        if body.revision != previous["revision"]:
            raise Conflict("Séance modifiée entre-temps. Recharge le planning.")
        value = body.model_dump(mode="json", exclude={"revision"})
        if value["activity_id"]:
            if value["status"] != "completed":
                raise ValueError("Retire le lien Garmin pour changer le statut.")
            validate_link(value["activity_id"], key)
        history = previous.get("history", [])[-49:] + [
            {
                k: previous.get(k)
                for k in (
                    "day",
                    "time",
                    "title",
                    "sport",
                    "status",
                    "duration_minutes",
                    "instructions",
                    "activity_id",
                    "updated_at",
                )
            }
        ]
        value = {
            **previous,
            **value,
            "revision": previous["revision"] + 1,
            "updated_at": db.now(),
            "history": history,
        }
        db.upsert_record("planned_session", key, value)
        return value


def propose(items, assistant_id):
    accepted = []
    today = datetime.now(ZoneInfo(db.profile()["timezone"])).date()
    for raw in items[:5] if isinstance(items, list) else []:
        if not isinstance(raw, dict):
            continue
        try:
            # A model can suggest future workouts, never mark them done or attach Garmin IDs.
            body = Session.model_validate({**raw, "status": "proposed", "activity_id": None})
            if not today <= body.day <= today + timedelta(days=366):
                continue
            if any(
                p["day"] == body.day.isoformat()
                and p["sport"] == body.sport
                and p["title"] == body.title
                for p in accepted
            ):
                continue
            existing = calendar(body.day, body.day)["sessions"]
            if any(
                p["day"] == body.day.isoformat()
                and p["sport"] == body.sport
                and p["title"] == body.title
                and p["status"] not in {"cancelled", "dismissed"}
                for p in existing
            ):
                continue
            accepted.append(create(body, source="coach", message_id=assistant_id))
        except ValueError:
            continue
    return accepted


def calendar(start, end):
    if end < start or (end - start).days > 92:
        raise ValueError("Choisir une période de 93 jours maximum.")
    params = {
        "u": user_id(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "a": (start - timedelta(days=1)).isoformat(),
        "b": (end + timedelta(days=1)).isoformat(),
    }
    with db.connection() as conn:
        plans = conn.execute(
            text(
                "SELECT data FROM records WHERE user_id=:u AND kind='planned_session' "
                "AND json_extract(data,'$.day') BETWEEN :start AND :end ORDER BY "
                "json_extract(data,'$.day'),json_extract(data,'$.time') LIMIT 401"
            ),
            params,
        ).all()
        rows = conn.execute(
            text(
                "SELECT record_key,data FROM records WHERE user_id=:u AND kind='activity' "
                "AND substr(COALESCE(json_extract(data,'$.startTimeLocal'),json_extract(data,'$.startTimeGMT')),1,10) "
                "BETWEEN :a AND :b ORDER BY json_extract(data,'$.startTimeLocal') LIMIT 501"
            ),
            params,
        ).all()
    actual = []
    for key, serialized in rows:
        a = json.loads(serialized)
        local = a.get("startTimeLocal")
        if not local and a.get("startTimeGMT"):
            try:
                stamp = datetime.fromisoformat(a["startTimeGMT"].replace("Z", "+00:00"))
                local = (
                    (stamp if stamp.tzinfo else stamp.replace(tzinfo=ZoneInfo("UTC")))
                    .astimezone(ZoneInfo(db.profile()["timezone"]))
                    .isoformat()
                )
            except ValueError:
                continue
        day = (local or "")[:10]
        if start.isoformat() <= day <= end.isoformat():
            actual.append(
                {
                    "id": key,
                    "day": day,
                    "time": (local or "")[11:16],
                    **{
                        k: a.get(k)
                        for k in ("activityName", "activityType", "duration", "distance")
                    },
                }
            )
    return {
        "sessions": [
            {k: v for k, v in json.loads(r[0]).items() if k != "history"} for r in plans[:400]
        ],
        "activities": actual[:500],
        "limited": len(plans) > 400 or len(rows) > 500,
        "timezone": db.profile()["timezone"],
    }


def context():
    today = datetime.now(ZoneInfo(db.profile()["timezone"])).date()
    return {
        "timezone": db.profile()["timezone"],
        "today": today.isoformat(),
        "sessions": calendar(today - timedelta(days=14), today + timedelta(days=60))["sessions"],
        "rule": "proposed attend confirmation ; planned est prévu ; completed est déclaré réalisé ou lié à Garmin. Ne pas compter deux fois une séance liée.",
    }
