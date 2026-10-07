import logging
from datetime import date, datetime, timedelta
from getpass import getpass
from zoneinfo import ZoneInfo

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from coach import db
from coach.config import data_dir


def session_path():
    path = data_dir() / "garmin"
    path.mkdir(mode=0o700, exist_ok=True)
    return str(path)


def authenticate(reauth: bool = False) -> bool:
    """Interactive local login; credentials never pass through the web application."""
    logging.getLogger("garminconnect").setLevel(logging.CRITICAL)
    if not reauth:
        try:
            client = Garmin()
            client.login(session_path())
            client.get_user_summary(date.today().isoformat())
            return True
        except GarminConnectAuthenticationError:
            pass
    email = input("E-mail Garmin : ").strip()
    password = getpass("Mot de passe Garmin : ")
    client = Garmin(
        email=email, password=password, prompt_mfa=lambda: getpass("Code Garmin : ").strip()
    )
    del password
    try:
        client.login(session_path())
        client.get_user_summary(date.today().isoformat())
    finally:
        client.password = None
    return False


def sync(days: int = 7) -> dict:
    """Idempotent sync. Persist successful sources; never replace missing values with zero."""
    client = Garmin()
    client.login(session_path())
    today = datetime.now(ZoneInfo(db.profile()["timezone"])).date()
    report = {"synced_at": db.now(), "activities": 0, "days": 0, "errors": []}
    activities = client.get_activities(0, 100)
    for activity in activities:
        if activity.get("activityId") is not None:
            db.upsert_record("activity", str(activity["activityId"]), activity)
            report["activities"] += 1
    methods = {
        "summary": client.get_user_summary,
        "sleep": client.get_sleep_data,
        "heart_rate": client.get_heart_rates,
        "hrv": client.get_hrv_data,
        "readiness": client.get_training_readiness,
    }
    for offset in range(days):
        day = (today - timedelta(days=offset)).isoformat()
        previous = next((r["data"] for r in db.records("health", 366) if r["key"] == day), {})
        values = dict(previous)
        for name, fetch in methods.items():
            try:
                value = fetch(day)
                if value:
                    values[name] = value
            except (GarminConnectAuthenticationError, GarminConnectTooManyRequestsError):
                raise
            except Exception as exc:
                report["errors"].append({"date": day, "source": name, "type": type(exc).__name__})
        if values:
            db.upsert_record("health", day, values)
            report["days"] += 1
    db.upsert_record("integration", "garmin", report)
    return report
