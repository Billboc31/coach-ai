"""Invite-only accounts. Random personal keys and one-use invitations; no public signup."""

import hashlib
import os
import secrets
import threading
import time
import uuid

from coach.config import root_data_dir, user_id, user_scope
from coach.secrets import read_secret, write_secret

lock = threading.RLock()


def registry():
    return {"users": {}, "invitations": {}, **read_secret(root_data_dir() / "accounts.json")}


def save(value):
    write_secret(root_data_dir() / "accounts.json", value)


def fingerprint(key):
    return hashlib.sha256(key.encode()).hexdigest()


def key_hash(key, salt):
    return hashlib.pbkdf2_hmac("sha256", key.encode(), bytes.fromhex(salt), 600000).hex()


def authenticate(key):
    owner_key = os.environ.get("COACH_ACCESS_KEY") or read_secret(root_data_dir() / "app.json").get(
        "access_key", ""
    )
    if owner_key and secrets.compare_digest(owner_key.encode(), key.encode()):
        return "local"
    index = fingerprint(key)
    with lock:
        candidates = registry()["users"].items()
        for owner, value in candidates:
            if secrets.compare_digest(value["key_index"], index) and secrets.compare_digest(
                value["key_hash"], key_hash(key, value["salt"])
            ):
                return owner
    return None


def users():
    with lock:
        return ["local", *registry()["users"]]


def identity():
    owner = user_id()
    if owner == "local":
        return {"id": owner, "name": "Administrateur", "admin": True}
    with lock:
        account = registry()["users"].get(owner)
    if not account:
        raise ValueError("Compte introuvable")
    return {"id": owner, "name": account["name"], "admin": False}


def invite(label):
    key = secrets.token_urlsafe(32)
    value = {
        "id": uuid.uuid4().hex,
        "label": label,
        "created_at": time.time(),
        "expires_at": time.time() + 7 * 86400,
    }
    with lock:
        data = registry()
        data["invitations"] = {
            k: v
            for k, v in data["invitations"].items()
            if v["expires_at"] > time.time() and not v.get("used_at")
        }
        if len(data["invitations"]) >= 100:
            raise ValueError(
                "100 invitations actives maximum ; annule les invitations inutilisées."
            )
        data["invitations"][fingerprint(key)] = value
        save(data)
    return {**value, "invite_key": key}


def invitations():
    with lock:
        return list(registry()["invitations"].values())


def revoke(invitation_id):
    with lock:
        data = registry()
        found = next((k for k, v in data["invitations"].items() if v["id"] == invitation_id), None)
        if found is None:
            return False
        del data["invitations"][found]
        save(data)
        return True


def register(invite_key, name):
    key = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    hashed = key_hash(key, salt)
    with lock:
        data = registry()
        invitation = data["invitations"].get(fingerprint(invite_key))
        if not invitation or invitation.get("used_at") or invitation["expires_at"] <= time.time():
            raise ValueError("Invitation invalide, expirée ou déjà utilisée.")
        if len(data["users"]) >= 500:
            raise ValueError("Nombre maximal de comptes atteint.")
        owner = "u_" + uuid.uuid4().hex
        data["users"][owner] = {
            "name": name,
            "salt": salt,
            "key_hash": hashed,
            "key_index": fingerprint(key),
            "created_at": time.time(),
        }
        from coach import db

        with user_scope(owner):
            profile = db.profile()
            profile["name"] = name
            db.save_profile(profile)
        invitation["used_at"] = time.time()
        save(data)
    return {"id": owner, "name": name, "access_key": key}
