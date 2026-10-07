import logging
import re
from datetime import date, datetime, timedelta
from getpass import getpass
from zoneinfo import ZoneInfo

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from coach import db
from coach.config import data_dir


def safe_failure(exc: Exception) -> str:
    """Classify failures without printing provider bodies, URLs or credentials."""
    chain = []
    current = exc
    while current is not None and len(chain) < 8 and all(current is not e for e in chain):
        chain.append(current)
        current = current.__cause__ or current.__context__
    if any(isinstance(e, GarminConnectTooManyRequestsError) for e in chain):
        return "Garmin limite les tentatives (429). Attendre avant de réessayer."
    if any(isinstance(e, GarminConnectAuthenticationError) for e in chain):
        return "Authentification refusée. Vérifier le compte dans Garmin Connect."
    # Read text for classification only; never return even a truncated original error.
    diagnostic = " ".join(str(e).lower() for e in chain)
    if re.search(r"(?:http|status|returned|api error)\s*[:=]?\s*403\b", diagnostic):
        return "Garmin refuse la requête HTTP (403). Cause exacte non confirmée."
    if re.search(r"(?:http|status|returned|api error)\s*[:=]?\s*429\b", diagnostic):
        return "Garmin limite les tentatives (429). Attendre avant de réessayer."
    if "timeout" in diagnostic or "timed out" in diagnostic:
        return "Délai de connexion à Garmin dépassé."
    if any(word in diagnostic for word in ("resolve host", "name resolution", "getaddrinfo")):
        return "Résolution DNS Garmin impossible depuis le serveur."
    if any(word in diagnostic for word in ("certificate verify", "sslerror", "ssl certificate")):
        return "Échec de vérification du certificat TLS Garmin."
    return "Connexion Garmin impossible ; cause non déterminée par le connecteur."


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
        print("Connexion à Garmin en cours…", flush=True)
        client.login(session_path())
        print("Vérification de l’accès aux données Garmin…", flush=True)
        client.get_user_summary(date.today().isoformat())
    except (
        GarminConnectConnectionError,
        GarminConnectAuthenticationError,
        GarminConnectTooManyRequestsError,
    ) as exc:
        raise ValueError(safe_failure(exc)) from None
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
