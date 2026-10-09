"""Owner-scoped, short-lived credential login. No passwords or MFA codes on disk."""

import logging
import queue
import secrets
import tempfile
import threading
import time
from contextvars import copy_context
from datetime import date
from pathlib import Path

from garminconnect import Garmin

from coach.config import data_dir
from coach.garmin import safe_failure, session_path, validate_session
from coach.garmin_lock import storage_lock
from coach.owner_resources import OwnerResource
from coach.secrets import read_secret, write_secret

TTL = 300
ACTIVE = {"connecting", "awaiting_mfa", "verifying", "cancelling"}
states = OwnerResource(lambda: {"attempt": None, "starts": [], "guard": threading.RLock()})


class LoginConflict(ValueError):
    pass


class LoginLimited(ValueError):
    pass


class Aborted(Exception):
    pass


def _check(attempt):
    if attempt["cancelled"]:
        raise Aborted("Connexion annulée.")
    if time.monotonic() >= attempt["deadline"]:
        raise Aborted("Connexion expirée. Relance une tentative.")


def _expire(attempt):
    if attempt["status"] in ACTIVE and time.monotonic() >= attempt["deadline"]:
        attempt.update(cancelled=True, status="cancelling", message="Connexion expirée.")
        try:
            attempt["codes"].put_nowait(None)
        except queue.Full:
            pass


def _view(attempt):
    if not attempt:
        return {"status": "idle"}
    return {key: attempt[key] for key in ("id", "status", "expires_at", "message")}


def status():
    state = states.current()
    with state["guard"]:
        if state["attempt"]:
            _expire(state["attempt"])
        return _view(state["attempt"])


def _matching(state, attempt_id):
    attempt = state["attempt"]
    if not attempt or not secrets.compare_digest(attempt["id"], attempt_id):
        raise LoginConflict("Tentative introuvable. Actualise Connexions.")
    _expire(attempt)
    return attempt


def submit_code(attempt_id, code):
    state = states.current()
    with state["guard"]:
        attempt = _matching(state, attempt_id)
        if attempt["status"] != "awaiting_mfa":
            raise LoginConflict("Cette tentative n’attend pas de code Garmin.")
        attempt.update(status="connecting", message="Vérification du code Garmin…")
        attempt["codes"].put_nowait(code)
        return _view(attempt)


def cancel(attempt_id):
    state = states.current()
    with state["guard"]:
        attempt = _matching(state, attempt_id)
        if attempt["status"] in ACTIVE:
            attempt.update(cancelled=True, status="cancelling", message="Annulation en cours…")
            try:
                attempt["codes"].put_nowait(None)
            except queue.Full:
                pass
        return _view(attempt)


def start(email, password, operation_lock):
    state = states.current()
    with state["guard"]:
        current = state["attempt"]
        if current and current["status"] in ACTIVE:
            raise LoginConflict("Une connexion Garmin est déjà en cours.")
        now = time.monotonic()
        state["starts"] = [stamp for stamp in state["starts"] if stamp > now - 600]
        if len(state["starts"]) >= 3:
            raise LoginLimited("Trois tentatives en dix minutes. Attends avant de réessayer.")
        if not operation_lock.acquire(blocking=False):
            raise LoginConflict("Une opération Garmin est en cours. Attends sa fin.")
        attempt = {
            "id": secrets.token_urlsafe(24),
            "status": "connecting",
            "message": "Connexion à Garmin…",
            "expires_at": time.time() + TTL,
            "deadline": now + TTL,
            "cancelled": False,
            "codes": queue.Queue(maxsize=1),
        }
        state["attempt"] = attempt
        state["starts"].append(now)
        credentials = {"email": email, "password": password}
        context = copy_context()
        thread = threading.Thread(
            target=lambda: context.run(_worker, state, attempt, credentials, operation_lock),
            daemon=True,
            name="garmin-login",
        )
        try:
            thread.start()
        except Exception:
            credentials.clear()
            operation_lock.release()
            attempt.update(status="failed", message="Connexion indisponible.")
            raise LoginConflict("Connexion indisponible.") from None
        return _view(attempt)


def _worker(state, attempt, credentials, operation_lock):
    client = None
    try:
        logging.getLogger("garminconnect").setLevel(logging.CRITICAL)

        def mfa():
            with state["guard"]:
                _check(attempt)
                client.password = None
                attempt.update(status="awaiting_mfa", message="Saisis le code envoyé par Garmin.")
            try:
                code = attempt["codes"].get(timeout=max(0, attempt["deadline"] - time.monotonic()))
            except queue.Empty:
                raise Aborted("Code Garmin non reçu. Connexion expirée.") from None
            with state["guard"]:
                _check(attempt)
            if code is None:
                raise Aborted("Connexion annulée.")
            return code

        client = Garmin(
            email=credentials.pop("email"),
            password=credentials.pop("password"),
            prompt_mfa=mfa,
            retry_attempts=0,
        )
        # A refusal must stop this attempt. Disable the adapter's TLS fingerprint
        # and alternate-login fallback chain, retaining its plain HTTP strategy.
        client.client.skip_strategies = {
            "mobile+cffi",
            "widget+cffi",
            "portal+cffi",
            "portal+requests",
        }
        credentials.clear()
        with storage_lock():
            # Login and token rotations happen in a staging directory. Never hand
            # the provider the active token file during a replacement attempt.
            with tempfile.TemporaryDirectory(prefix="garmin-login-", dir=data_dir()) as folder:
                client.login(folder)
                client.password = None
                with state["guard"]:
                    _check(attempt)
                    attempt.update(status="verifying", message="Vérification de l’accès Garmin…")
                client.get_user_summary(date.today().isoformat())
                client.client.dump(folder)
                value = validate_session(read_secret(Path(folder) / "garmin_tokens.json"))
                with state["guard"]:
                    _check(attempt)
                    write_secret(Path(session_path()) / "garmin_tokens.json", value)
                    attempt.update(
                        status="completed", message="Session Garmin validée et enregistrée."
                    )
    except Exception as exc:
        with state["guard"]:
            if attempt["cancelled"] or isinstance(exc, Aborted):
                attempt.update(
                    status="cancelled" if attempt["cancelled"] else "expired",
                    message="Connexion expirée. Relance une tentative."
                    if time.monotonic() >= attempt["deadline"]
                    else "Connexion annulée.",
                )
            else:
                attempt.update(status="failed", message=safe_failure(exc))
    finally:
        credentials.clear()
        if client is not None:
            client.password = None
        with state["guard"]:
            while not attempt["codes"].empty():
                attempt["codes"].get_nowait()
        operation_lock.release()
