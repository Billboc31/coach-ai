"""Persistent, single-user Garmin imports with bounded progress and resumable checkpoints."""

import hashlib
import logging
import threading
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from coach import db
from coach.garmin import safe_failure, session_path
from coach.garmin_lock import storage_lock

control = threading.Lock()
stop = threading.Event()
ACTIVE = {"running", "waiting", "cancelling"}


def status():
    return db.record("sync_job", "garmin") or None


def save(job):
    job["updated_at"] = db.now()
    db.upsert_record("sync_job", "garmin", job)


def launch(lock, *, mode="range", start=None, end=None, resume=False, origin="manual"):
    with control:
        previous = status()
        if (
            origin == "automatic"
            and previous
            and previous.get("origin", "manual") == "manual"
            and previous["status"] != "completed"
        ):
            raise ValueError("Un import manuel reste à reprendre.")
        if not lock.acquire(blocking=False):
            raise ValueError("Une synchronisation Garmin est déjà en cours.")
        try:
            if resume:
                if not previous or previous["status"] == "completed":
                    raise ValueError("Aucun import à reprendre.")
                job = previous
                # Activity list offsets can shift when new activities arrive; replay is idempotent.
                if job["phase"] == "activities":
                    job["offset"] = 0
                    job["activities"] = 0
                    job["oldest_activity"] = None
                    job["page_signature"] = None
                job.update(status="running", error=None, retries=0)
            else:
                today = datetime.now(ZoneInfo(db.profile()["timezone"])).date()
                end = end or today
                if mode not in {"range", "all"} or end > today:
                    raise ValueError("Période invalide.")
                if mode == "range" and start is None:
                    start = end - timedelta(days=6)
                if start and (start > end or start < date(1990, 1, 1)):
                    raise ValueError("Période invalide.")
                job = {
                    "id": uuid.uuid4().hex,
                    "origin": origin,
                    "status": "running",
                    "phase": "activities",
                    "mode": mode,
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat(),
                    "offset": 0,
                    "activities": 0,
                    "oldest_activity": None,
                    "days_processed": 0,
                    "days_with_data": 0,
                    "total_days": None,
                    "current_date": None,
                    "errors": 0,
                    "error_samples": [],
                    "error": None,
                    "retries": 0,
                    "started_at": db.now(),
                }
            save(job)
            stop.clear()
            spawn(job, lock)
            return dict(job)
        except Exception:
            lock.release()
            raise


def spawn(job, lock):
    threading.Thread(target=worker, args=(job, lock), daemon=True, name="garmin-import").start()


def cancel():
    with control:
        job = status()
        if job and job["status"] in ACTIVE:
            stop.set()
        return job


def recover(lock):
    job = status()
    if job and job["status"] in ACTIVE:
        launch(lock, resume=True)


def worker(job, lock):
    try:
        with storage_lock():
            work_locked(job)
    except Exception as exc:
        job.update(
            status="failed", error=str(exc) if isinstance(exc, ValueError) else safe_failure(exc)
        )
        save(job)
    finally:
        lock.release()


def work_locked(job):
    logging.getLogger("garminconnect").setLevel(logging.CRITICAL)
    try:
        while True:
            try:
                client = Garmin()
                client.login(session_path())
                run(job, client)
                job["status"] = "cancelled" if stop.is_set() else "completed"
                job["finished_at"] = db.now()
                save(job)
                if job["status"] == "completed":
                    db.upsert_record(
                        "integration",
                        "garmin",
                        {
                            "synced_at": db.now(),
                            "activities": job["activities"],
                            "days": job["days_with_data"],
                            "errors": job["error_samples"],
                            "start": job["start"],
                            "end": job["end"],
                        },
                    )
                return
            except GarminConnectTooManyRequestsError:
                job["retries"] += 1
                job["error"] = safe_failure(GarminConnectTooManyRequestsError())
                if job["retries"] > 3:
                    job["status"] = "paused"
                    save(job)
                    return
                delay = 60 * (2 ** (job["retries"] - 1))
                job.update(status="waiting", retry_seconds=delay)
                save(job)
                if stop.wait(delay):
                    job["status"] = "cancelled"
                    save(job)
                    return
                job.update(status="running", error=None)
                save(job)
    except Exception as exc:
        job.update(status="failed", error=safe_failure(exc))
        save(job)


def run(job, client, pace=0.25):
    """Commit each page/day before advancing its cursor; a replay cannot duplicate records."""
    start = date.fromisoformat(job["start"]) if job["start"] else None
    end = date.fromisoformat(job["end"])
    while job["phase"] == "activities" and not stop.is_set():
        batch = client.get_activities(job["offset"], 100)
        if not isinstance(batch, list):
            raise ValueError("Unexpected Garmin response")
        if batch:
            signature = hashlib.sha256(
                repr([a.get("activityId") for a in batch]).encode()
            ).hexdigest()
            if signature == job.get("page_signature"):
                raise ValueError("Garmin repeated an activity page")
            job["page_signature"] = signature
        oldest = None
        for activity in batch:
            raw = activity.get("startTimeLocal") or activity.get("startTimeGMT") or ""
            try:
                day = date.fromisoformat(raw[:10])
            except ValueError:
                day = None
            if day:
                oldest = min(oldest, day) if oldest else day
                previous = job["oldest_activity"]
                if not previous or day.isoformat() < previous:
                    job["oldest_activity"] = day.isoformat()
            in_period = job["mode"] == "all" or (day and start <= day <= end)
            if activity.get("activityId") is not None and in_period:
                db.upsert_record("activity", str(activity["activityId"]), activity)
                job["activities"] += 1
        job["offset"] += len(batch)
        # Garmin lists newest first. A full page older than the start ends a range import.
        done = (
            not batch or len(batch) < 100 or (job["mode"] == "range" and oldest and oldest < start)
        )
        if done:
            if start is None:
                start = (
                    date.fromisoformat(job["oldest_activity"]) if job["oldest_activity"] else end
                )
                start = min(start, end)
                job["start"] = start.isoformat()
            job.update(
                phase="health", current_date=end.isoformat(), total_days=(end - start).days + 1
            )
        save(job)
        if stop.wait(pace):
            return
    sources = {
        "summary": "get_user_summary",
        "sleep": "get_sleep_data",
        "heart_rate": "get_heart_rates",
        "hrv": "get_hrv_data",
        "readiness": "get_training_readiness",
        "stress": "get_stress_data",
        "body_battery": "get_body_battery",
        "respiration": "get_respiration_data",
        "spo2": "get_spo2_data",
        "body_composition": "get_body_composition",
    }
    while job["phase"] == "health" and not stop.is_set():
        day = date.fromisoformat(job["current_date"])
        if day < start:
            return
        key = day.isoformat()
        values = db.record("health", key)
        provenance = values.setdefault("_sources", {})
        has_data = False
        for source, method in sources.items():
            if stop.is_set():
                return
            try:
                value = getattr(client, method)(key)
                if value:
                    values[source] = value
                    has_data = True
                provenance[source] = {"status": "ok" if value else "empty", "read_at": db.now()}
            except (GarminConnectAuthenticationError, GarminConnectTooManyRequestsError):
                raise
            except Exception as exc:
                # A definitive HTTP 403 must stop the import, not trigger repeated requests.
                if "(403)" in safe_failure(exc):
                    raise
                provenance[source] = {
                    "status": "unavailable",
                    "read_at": db.now(),
                    "error_type": type(exc).__name__,
                }
                job["errors"] += 1
                if len(job["error_samples"]) < 20:
                    job["error_samples"].append(
                        {"date": key, "source": source, "type": type(exc).__name__}
                    )
            if stop.wait(pace):
                return
        db.upsert_record("health", key, values)
        job["days_processed"] += 1
        job["days_with_data"] += int(has_data)
        job["current_date"] = (day - timedelta(days=1)).isoformat()
        save(job)
