import json
import os
import secrets
import threading
import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from coach import chatgpt, db
from coach.config import data_dir, web_settings
from coach.secrets import read_secret

settings = web_settings()
app = FastAPI(title="Coach AI", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts)
sessions: dict[str, float] = {}
login_attempts: dict[str, list[float]] = {}
chat_lock = threading.Lock()
sync_lock = threading.Lock()
ALLOWED_ORIGINS = settings.origins


@app.middleware("http")
async def local_guard(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") not in ALLOWED_ORIGINS:
            return Response(status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def require_session(request: Request):
    value = request.cookies.get("coach_session", "")
    if sessions.get(value, 0) < time.time():
        sessions.pop(value, None)
        raise HTTPException(401, "Saisis ta clé d’accès.")


class Login(BaseModel):
    access_key: str = Field(min_length=1, max_length=200)


class Profile(BaseModel):
    name: str = Field(default="", max_length=100)
    timezone: str = "Europe/Paris"
    goals: str = Field(default="", max_length=5000)
    constraints: str = Field(default="", max_length=5000)
    sports: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError("Fuseau horaire inconnu") from None
        return value


class Note(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class Chat(Note):
    model: str = Field(min_length=1, max_length=100)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    remote = request.client.host if request.client else "unknown"
    stamp = time.time()
    attempts = [t for t in login_attempts.get(remote, []) if t > stamp - 60]
    login_attempts[remote] = attempts
    if len(attempts) >= 5:
        raise HTTPException(429, "Trop d’essais ; attends une minute.")
    attempts.append(stamp)
    key = os.environ.get("COACH_ACCESS_KEY") or read_secret(data_dir() / "app.json").get(
        "access_key", ""
    )
    if not key or not secrets.compare_digest(key, body.access_key):
        raise HTTPException(401, "Clé incorrecte.")
    login_attempts.pop(remote, None)
    for token, expires in list(sessions.items()):
        if expires < stamp:
            sessions.pop(token)
    token = secrets.token_urlsafe(32)
    sessions[token] = stamp + 8 * 3600
    response.set_cookie(
        "coach_session",
        token,
        httponly=True,
        samesite="strict",
        max_age=8 * 3600,
        secure=settings.production,
    )
    return {"ok": True}


@app.post("/api/logout", dependencies=[Depends(require_session)])
def logout(request: Request, response: Response):
    sessions.pop(request.cookies.get("coach_session", ""), None)
    response.delete_cookie(
        "coach_session", secure=settings.production, httponly=True, samesite="strict"
    )
    return {"ok": True}


@app.get("/api/dashboard", dependencies=[Depends(require_session)])
def dashboard():
    garmin = db.records("integration", 5)
    account = read_secret(chatgpt.credential_path())
    activities = sorted(
        db.records("activity", 100), key=lambda r: r["data"].get("startTimeGMT", ""), reverse=True
    )
    return {
        "profile": db.profile(),
        "activities": activities[:20],
        "health": db.records("health", 7),
        "notes": db.history("notes", 20),
        "messages": db.history("messages", 40),
        "integrations": {
            "garmin": next((r["data"] for r in garmin if r["key"] == "garmin"), None),
            "chatgpt": {
                "configured": bool(account.get("access_token")),
                "plan_authorized": "chatgpt.tokens.use.direct" in account.get("scope", "").split(),
            },
        },
    }


@app.put("/api/profile", dependencies=[Depends(require_session)])
def update_profile(body: Profile):
    db.save_profile(body.model_dump())
    return body


@app.post("/api/notes", dependencies=[Depends(require_session)])
def add_note(body: Note):
    if not body.content.strip():
        raise HTTPException(422, "Note vide.")
    db.append("notes", body.content.strip())
    return {"ok": True}


@app.post("/api/garmin/session", dependencies=[Depends(require_session)])
async def receive_garmin_session(request: Request):
    # Manual parsing avoids Pydantic echoing rejected credential input in a 422 response.
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 65536:
            raise HTTPException(413, "Session trop volumineuse.")
    from coach.garmin import import_session, safe_failure, validate_session

    try:
        value = validate_session(json.loads(payload))
    except (ValueError, UnicodeError):
        raise HTTPException(422, "Format de session Garmin incompatible.") from None
    if not sync_lock.acquire(blocking=False):
        raise HTTPException(409, "Synchronisation déjà en cours.")
    try:
        await run_in_threadpool(import_session, value)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(502, safe_failure(exc)) from None
    finally:
        sync_lock.release()


@app.post("/api/garmin/sync", dependencies=[Depends(require_session)])
def sync_garmin():
    if not sync_lock.acquire(blocking=False):
        raise HTTPException(409, "Synchronisation déjà en cours.")
    try:
        from coach.garmin import sync

        return sync(7)
    except Exception as exc:
        raise HTTPException(
            502,
            "Synchronisation impossible : "
            + type(exc).__name__
            + ". Vérifie la connexion Garmin dans le terminal.",
        ) from None
    finally:
        sync_lock.release()


@app.get("/api/models", dependencies=[Depends(require_session)])
def list_models():
    try:
        with chat_lock:
            return chatgpt.models()
    except Exception:
        raise HTTPException(503, "Connecte ou reconnecte ChatGPT dans le terminal.") from None


def coach_context():
    # Small curated context, not a vector RAG yet. Avoid sending GPS tracks and raw device data.
    activities = []
    for record in db.records("activity", 100):
        a = record["data"]
        activities.append(
            {
                k: a.get(k)
                for k in [
                    "activityName",
                    "activityType",
                    "startTimeGMT",
                    "distance",
                    "duration",
                    "averageHR",
                    "maxHR",
                ]
            }
        )
    activities.sort(key=lambda a: a.get("startTimeGMT") or "", reverse=True)
    recovery = []
    for record in db.records("health", 7):
        h = record["data"]
        summary = h.get("summary") or {}
        sleep = (h.get("sleep") or {}).get("dailySleepDTO") or {}
        recovery.append(
            {
                "date": record["key"],
                "steps": summary.get("totalSteps"),
                "resting_hr": (h.get("heart_rate") or {}).get("restingHeartRate"),
                "sleep_seconds": sleep.get("sleepTimeSeconds"),
                "hrv": (h.get("hrv") or {}).get("hrvSummary"),
                "readiness": h.get("readiness"),
            }
        )
    return {
        "as_of": db.now(),
        "profile": db.profile(),
        "recent_activities": activities[:10],
        "activity_units": {"distance": "meters", "duration": "seconds", "heart_rate": "bpm"},
        "recovery": recovery,
        "notes": [
            {"content": r["content"], "date": r["created_at"]} for r in db.history("notes", 10)
        ],
    }


@app.post("/api/chat", dependencies=[Depends(require_session)])
def chat(body: Chat):
    if not body.content.strip():
        raise HTTPException(422, "Message vide.")
    if not chat_lock.acquire(blocking=False):
        raise HTTPException(409, "Le coach répond déjà à un message.")
    try:
        messages = db.history("messages", 20) + [{"role": "user", "content": body.content}]
        answer, usage = chatgpt.respond(body.model, coach_context(), messages)
        if not answer.strip():
            raise ValueError("Réponse vide.")
        db.append("messages", body.content, "user")
        db.append("messages", answer, "assistant")
        db.upsert_record("integration", "chatgpt", {"last_response_at": db.now(), "usage": usage})
        return {"content": answer, "usage": usage}
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from None
    except Exception:
        raise HTTPException(
            502, "Le coach est indisponible ; aucun conseil partiel enregistré."
        ) from None
    finally:
        chat_lock.release()


frontend = Path(
    os.environ.get(
        "COACH_FRONTEND_DIR", str(Path(__file__).resolve().parents[2] / "frontend" / "dist")
    )
)
if frontend.exists():
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(frontend / "index.html")
