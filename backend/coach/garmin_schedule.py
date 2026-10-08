"""Durable polling schedule; shares the manual import's lock and checkpoints."""

import threading
from datetime import datetime, timedelta, timezone
from threading import Thread
from zoneinfo import ZoneInfo

from coach import accounts, db, garmin_jobs
from coach.config import data_dir, user_scope

control = threading.Lock()
INTERVALS = {30, 60, 180, 360, 1440}


def state():
    return {
        "enabled": True,
        "minutes": 60,
        "next_run": None,
        "error": None,
        **db.record("settings", "garmin_schedule"),
    }


def configure(enabled, minutes):
    if minutes not in INTERVALS:
        raise ValueError("Fréquence invalide.")
    with control:
        value = state()
        value.update(
            enabled=enabled,
            minutes=minutes,
            error=None,
            acknowledged_job=(garmin_jobs.status() or {}).get("id"),
            next_run=(datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(),
        )
        db.upsert_record("settings", "garmin_schedule", value)
        return value


def tick(lock, instant=None):
    instant = instant or datetime.now(timezone.utc)
    with control:
        value = state()
        if not value["enabled"] or not (data_dir() / "garmin" / "garmin_tokens.json").exists():
            return
        job = garmin_jobs.status()
        if lock.locked() or (job and job["status"] in garmin_jobs.ACTIVE):
            return
        # Never replace a resumable manual backfill with a rolling automatic import.
        if job and job.get("origin", "manual") == "manual" and job["status"] != "completed":
            return
        if not value["next_run"]:
            value["next_run"] = (instant + timedelta(minutes=value["minutes"])).isoformat()
            db.upsert_record("settings", "garmin_schedule", value)
            return
        if (
            job
            and job.get("origin") == "automatic"
            and job["status"] in {"failed", "paused"}
            and job.get("id") != value.get("acknowledged_job")
        ):
            value.update(
                enabled=False,
                error=job.get("error")
                or "Import interrompu. Réactive après vérification de Garmin.",
            )
        else:
            if instant < datetime.fromisoformat(value["next_run"]):
                return
            today = instant.astimezone(ZoneInfo(db.profile()["timezone"])).date()
            since = today - timedelta(days=2)
            last = db.record("integration", "garmin").get("synced_at")
            if last:
                since = min(
                    since,
                    datetime.fromisoformat(last)
                    .astimezone(ZoneInfo(db.profile()["timezone"]))
                    .date()
                    - timedelta(days=2),
                )
            try:
                garmin_jobs.launch(lock, start=since, end=today, origin="automatic")
            except ValueError:
                return  # Another manual request won the shared lock.
            value.update(last_run=instant.isoformat(), error=None)
        value["next_run"] = (instant + timedelta(minutes=value["minutes"])).isoformat()
        db.upsert_record("settings", "garmin_schedule", value)


def start(lock):
    stopping = threading.Event()

    def loop():
        while not stopping.is_set():
            try:
                for owner in accounts.users():
                    if stopping.is_set():
                        break
                    with user_scope(owner):
                        try:
                            tick(lock)
                        except Exception:
                            pass
            except Exception:
                # Storage/transient failures must not kill future scheduler ticks.
                pass
            stopping.wait(15)

    thread = Thread(target=loop, daemon=True, name="garmin-schedule")
    thread.start()
    return stopping, thread
