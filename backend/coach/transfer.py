"""Transfer authorized Garmin session directly to the owner's HTTPS deployment."""

from getpass import getpass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from coach.garmin import session_path, validate_session
from coach.secrets import read_secret


def transfer():
    value = validate_session(read_secret(Path(session_path()) / "garmin_tokens.json"))
    url = input("Adresse HTTPS de ton app Railway : ").strip().rstrip("/")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Saisir uniquement le domaine HTTPS de ton app.")
    print(f"Destination de la session Garmin : {parsed.netloc}", flush=True)
    key = getpass("Ta clé personnelle d’accès à cette app : ")
    # No redirects: neither the app key nor provider credentials may change destination.
    with httpx.Client(
        base_url=url, headers={"Origin": url}, timeout=180, follow_redirects=False
    ) as client:
        response = client.post("/api/login", json={"access_key": key})
        del key
        if response.status_code != 200:
            raise ValueError("Connexion à l’app refusée. Vérifier l’adresse et la clé privée.")
        try:
            print("Vérification de la session Garmin depuis Railway…", flush=True)
            response = client.post("/api/garmin/session", json=value)
            del value
            if response.status_code != 200:
                # The server sends only fixed, sanitized diagnostic strings.
                messages = {
                    409: "Une synchronisation Garmin est déjà en cours.",
                    422: "Format de session refusé par le serveur.",
                    413: "Session trop volumineuse.",
                    502: "Railway ne peut pas valider cette session auprès de Garmin."
                    " La session précédente est conservée.",
                }
                if response.status_code == 502:
                    try:
                        detail = response.json().get("detail", "")
                        if isinstance(detail, str) and "(403)" in detail:
                            messages[502] = "Garmin refuse aussi la session depuis Railway (403)."
                        elif isinstance(detail, str) and "(429)" in detail:
                            messages[502] = "Garmin limite les tentatives depuis Railway (429)."
                    except ValueError:
                        pass
                raise ValueError(
                    messages.get(response.status_code, "Transfert refusé. Vérifier le déploiement.")
                )
            print("Session Garmin validée et enregistrée sur Railway.", flush=True)
            response = client.post("/api/garmin/sync")
            if response.status_code != 200:
                raise ValueError("Session transférée ; synchronisation à relancer dans l’app.")
            report = response.json()
            print(f"Railway : {report['activities']} activités, {report['days']} jours.")
        finally:
            try:
                client.post("/api/logout")
            except httpx.HTTPError:
                pass


def transfer_chatgpt():
    from coach import chatgpt
    from coach.garmin_lock import storage_lock

    # Renew before copying if needed. After success only Railway owns refreshes.
    chatgpt.access_token()
    with storage_lock("chatgpt"):
        value = chatgpt.validate_session(read_secret(chatgpt.credential_path()))
        url = input("Adresse HTTPS de ton app Railway : ").strip().rstrip("/")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Saisir uniquement le domaine HTTPS de ton app.")
        print(f"Destination de la session ChatGPT : {parsed.netloc}", flush=True)
        key = getpass("Ta clé personnelle d’accès à cette app : ")
        with httpx.Client(
            base_url=url, headers={"Origin": url}, timeout=90, follow_redirects=False
        ) as client:
            response = client.post("/api/login", json={"access_key": key})
            del key
            if response.status_code != 200:
                raise ValueError("Connexion à l’app refusée. Vérifie l’adresse et la clé privée.")
            try:
                response = client.post("/api/chatgpt/session", json=value)
                if response.status_code != 200:
                    raise ValueError(
                        "Transfert ChatGPT refusé ; session locale conservée. "
                        "Vérifie le déploiement et réessaye."
                    )
                chatgpt.credential_path().unlink(missing_ok=True)
                print(
                    "Session ChatGPT validée sur Railway. Le poste est déconnecté ; "
                    "Railway gère désormais le renouvellement.",
                    flush=True,
                )
            finally:
                try:
                    client.post("/api/logout")
                except httpx.HTTPError:
                    pass
