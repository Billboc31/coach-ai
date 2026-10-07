import json
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from coach import chatgpt, db, garmin_jobs, memory
from coach.config import data_dir, web_settings
from coach.secrets import read_secret

settings = web_settings()


@asynccontextmanager
async def lifespan(app):
    garmin_jobs.recover(sync_lock)
    memory.recover()
    yield


app = FastAPI(title="Coach AI", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts)
sessions: dict[str, float] = {}
login_attempts: dict[str, list[float]] = {}
chat_lock = threading.Lock()
sync_lock = threading.Lock()
chatgpt_login = {"status": "idle"}
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


class SyncPeriod(BaseModel):
    mode: str = "range"
    start: date | None = None
    end: date | None = None

    @field_validator("mode")
    @classmethod
    def valid_mode(cls, value):
        if value not in {"range", "all"}:
            raise ValueError("Choisir range ou all")
        return value


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
    activities = db.activity_page(0, 20)
    return {
        "local_connections": not settings.production,
        "garmin_configured": (data_dir() / "garmin" / "garmin_tokens.json").exists(),
        "profile": db.profile(),
        "activities": activities[:20],
        "health": db.records("health", 7),
        "notes": db.history("notes", 20),
        "messages": db.history("messages", 40),
        "garmin_job": garmin_jobs.status(),
        "coverage": {"activities": db.coverage("activity"), "health": db.coverage("health")},
        "integrations": {
            "garmin": next((r["data"] for r in garmin if r["key"] == "garmin"), None),
            "chatgpt": {
                "configured": bool(account.get("access_token")),
                "plan_authorized": "chatgpt.tokens.use.direct" in account.get("scope", "").split(),
            },
        },
    }


@app.get("/api/activities", dependencies=[Depends(require_session)])
def activities_page(offset: int = 0):
    if offset < 0:
        raise HTTPException(422, "Pagination invalide.")
    return {"items": db.activity_page(offset, 50), "total": db.coverage("activity")["count"]}


@app.get("/api/garmin/jobs", dependencies=[Depends(require_session)])
def sync_status():
    return garmin_jobs.status()


@app.post("/api/garmin/jobs", status_code=202, dependencies=[Depends(require_session)])
def start_sync(body: SyncPeriod):
    try:
        return garmin_jobs.launch(sync_lock, mode=body.mode, start=body.start, end=body.end)
    except ValueError as exc:
        raise HTTPException(409 if sync_lock.locked() else 422, str(exc)) from None


@app.post("/api/garmin/jobs/resume", status_code=202, dependencies=[Depends(require_session)])
def resume_sync():
    try:
        return garmin_jobs.launch(sync_lock, resume=True)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@app.post("/api/garmin/jobs/cancel", dependencies=[Depends(require_session)])
def cancel_sync():
    return garmin_jobs.cancel()


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


async def private_payload(request: Request):
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 65536:
            raise HTTPException(413, "Session trop volumineuse.")
    try:
        return json.loads(payload)
    except (ValueError, UnicodeError):
        raise HTTPException(422, "Format de session incompatible.") from None


@app.post("/api/chatgpt/session", dependencies=[Depends(require_session)])
async def receive_chatgpt_session(request: Request):
    value = await private_payload(request)
    try:
        chatgpt.validate_session(value)
    except ValueError:
        raise HTTPException(
            422, "Session incompatible ou trop ancienne. Relance le test local."
        ) from None
    if not chat_lock.acquire(blocking=False):
        raise HTTPException(409, "Une opération ChatGPT est déjà en cours.")
    try:
        choices = await run_in_threadpool(chatgpt.import_session, value)
        return {"ok": True, "models": choices}
    except Exception:
        raise HTTPException(
            502,
            "Session ChatGPT non validée ; compte précédent conservé. "
            "Vérifie le compte, l’autorisation et la connexion réseau.",
        ) from None
    finally:
        chat_lock.release()


@app.post("/api/chatgpt/disconnect", dependencies=[Depends(require_session)])
def disconnect_chatgpt():
    if not chat_lock.acquire(blocking=False):
        raise HTTPException(409, "Une opération ChatGPT est déjà en cours.")
    try:
        chatgpt.disconnect()
        return {
            "ok": True,
            "message": "Connexion retirée de cette app. "
            "Pour révoquer l’autorisation, utilise les réglages ChatGPT.",
        }
    finally:
        chat_lock.release()


@app.post("/api/chatgpt/test", dependencies=[Depends(require_session)])
def test_chatgpt():
    if not chat_lock.acquire(blocking=False):
        raise HTTPException(409, "Une opération ChatGPT est déjà en cours.")
    try:
        choices = chatgpt.models()
        if not choices:
            raise ValueError("Aucun modèle disponible.")
        answer, _ = chatgpt.respond(
            choices[0]["id"], {}, [{"role": "user", "content": "Réponds : connexion réussie."}]
        )
        if not answer.strip():
            raise ValueError("Réponse vide.")
        return {"ok": True, "models": choices}
    except Exception:
        raise HTTPException(503, "Test ChatGPT échoué. Vérifie la session et le quota.") from None
    finally:
        chat_lock.release()


@app.post("/api/chatgpt/login", status_code=202, dependencies=[Depends(require_session)])
def start_chatgpt_login():
    if settings.production:
        raise HTTPException(409, "Autorise ChatGPT sur ton poste puis importe la session ici.")
    if not chat_lock.acquire(blocking=False):
        raise HTTPException(409, "Une opération ChatGPT est déjà en cours.")
    chatgpt_login.clear()
    chatgpt_login.update(status="starting")

    def worker():
        try:

            def ready(url):
                chatgpt_login.update(status="awaiting", url=url)

            chatgpt.sign_in(on_authorization=ready)
            chatgpt_login.clear()
            chatgpt_login.update(status="completed")
        except Exception:
            chatgpt_login.clear()
            chatgpt_login.update(
                status="failed", message="Autorisation échouée ou expirée. Réessaye."
            )
        finally:
            chat_lock.release()

    thread = threading.Thread(target=worker, daemon=True)
    try:
        thread.start()
    except Exception:
        chat_lock.release()
        raise HTTPException(503, "Connexion indisponible.") from None
    return {"status": "starting"}


@app.get("/api/chatgpt/login", dependencies=[Depends(require_session)])
def chatgpt_login_status():
    if settings.production:
        return {"status": "unavailable"}
    return dict(chatgpt_login)


@app.get("/api/models", dependencies=[Depends(require_session)])
def list_models():
    try:
        with chat_lock:
            return chatgpt.models()
    except Exception:
        raise HTTPException(503, "Connecte ou reconnecte ChatGPT dans Connexions.") from None


class MemoryFact(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    category: str = "preference"
    status: str = "active"
    expires_on: date | None = None

    @field_validator("content")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Souvenir vide")
        return value.strip()

    @field_validator("category")
    @classmethod
    def category_known(cls, value):
        if value not in memory.CATEGORIES:
            raise ValueError("Catégorie inconnue")
        return value

    @field_validator("status")
    @classmethod
    def status_known(cls, value):
        if value not in {"active", "proposed", "archived", "rejected"}:
            raise ValueError("Statut inconnu")
        return value


class MemoryRefresh(BaseModel):
    model: str = Field(min_length=1, max_length=100)


class MemorySettings(BaseModel):
    automatic: bool


@app.get("/api/memory", dependencies=[Depends(require_session)])
def memory_view():
    return memory.view()


@app.post("/api/memory/facts", dependencies=[Depends(require_session)])
def add_memory_fact(body: MemoryFact):
    try:
        return memory.edit_fact(
            None,
            body.content,
            body.category,
            body.expires_on.isoformat() if body.expires_on else None,
            body.status,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.put("/api/memory/facts/{key}", dependencies=[Depends(require_session)])
def edit_memory_fact(key: str, body: MemoryFact):
    try:
        return memory.edit_fact(
            key,
            body.content,
            body.category,
            body.expires_on.isoformat() if body.expires_on else None,
            body.status,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None


@app.delete("/api/memory/facts/{key}", dependencies=[Depends(require_session)])
def remove_memory_fact(key: str):
    try:
        memory.remove_fact(key)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None


@app.put("/api/memory/settings", dependencies=[Depends(require_session)])
def update_memory_settings(body: MemorySettings):
    memory.settings(body.automatic)
    return {"ok": True}


@app.post("/api/memory/refresh", status_code=202, dependencies=[Depends(require_session)])
def refresh_memory(body: MemoryRefresh):
    try:
        started = memory.launch(body.model, force=True)
        return {"started": started}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@app.delete("/api/memory/summary", dependencies=[Depends(require_session)])
def clear_memory_summary():
    with memory.mutation_lock:
        value = memory.state()
        value["summary"] = ""
        memory.save(value)
    return {"ok": True}


def coach_context(question="", recent_ids=()):
    # Small curated context, not a vector RAG yet. Avoid sending GPS tracks and raw device data.
    activities = []
    for record in db.activity_page(0, 20):
        a = record["data"]
        activities.append(
            {
                k: a.get(k)
                for k in [
                    "activityName",
                    "activityType",
                    "startTimeGMT",
                    "startTimeLocal",
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

        def fresh(source):
            state = h.get("_sources", {}).get(source, {}).get("status")
            return h.get(source) if state in {None, "ok"} else None

        summary = fresh("summary") or {}
        sleep = (fresh("sleep") or {}).get("dailySleepDTO") or {}
        recovery.append(
            {
                "date": record["key"],
                "steps": summary.get("totalSteps"),
                "resting_hr": (fresh("heart_rate") or {}).get("restingHeartRate"),
                "sleep_seconds": sleep.get("sleepTimeSeconds"),
                "hrv": (fresh("hrv") or {}).get("hrvSummary"),
                "readiness": fresh("readiness"),
                "sources": h.get("_sources", {}),
            }
        )
    selection = memory.activity_selection(question)
    if selection:
        selection["items"] = [
            {
                "activity_id": r["key"],
                **{
                    k: r["data"].get(k)
                    for k in (
                        "activityName",
                        "activityType",
                        "startTimeLocal",
                        "startTimeGMT",
                        "distance",
                        "duration",
                        "averageHR",
                        "maxHR",
                    )
                },
            }
            for r in selection["items"]
        ]
        selection["details_limited_to"] = 30
    return {
        "selected_activity_period": selection,
        "as_of": db.now(),
        "profile": db.profile(),
        "recent_activities": activities,
        "memory": memory.context(question, recent_ids),
        "history_months": db.activity_months(),
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
        suppressed = set(memory.state()["suppressed_ids"])
        recent = [m for m in db.history("messages", 20) if m["id"] not in suppressed]
        messages = recent + [{"role": "user", "content": body.content}]
        answer, usage = chatgpt.respond(
            body.model, coach_context(body.content, [m["id"] for m in recent]), messages
        )
        if not answer.strip():
            raise ValueError("Réponse vide.")
        db.append("messages", body.content, "user")
        db.append("messages", answer, "assistant")
        db.upsert_record("integration", "chatgpt", {"last_response_at": db.now(), "usage": usage})
        try:
            memory.launch(body.model)
        except Exception:
            pass  # A derived-memory failure must never discard a completed chat.
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
