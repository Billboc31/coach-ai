import concurrent.futures
import threading
import time

import pytest
from fastapi.testclient import TestClient

from coach import accounts, api, chatgpt, db, garmin_jobs, garmin_schedule, memory
from coach.config import data_dir, user_id, user_scope
from coach.secrets import read_secret, write_secret

ORIGIN = {"Origin": "http://localhost:8000"}


@pytest.fixture
def owner(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("COACH_ACCESS_KEY", raising=False)
    write_secret(tmp_path / "app.json", {"access_key": "synthetic-owner-key"})
    api.sessions.clear()
    api.session_owners.clear()
    api.login_attempts.clear()
    client = TestClient(api.app, headers=ORIGIN)
    assert client.post("/api/login", json={"access_key": "synthetic-owner-key"}).status_code == 200
    yield client
    client.close()
    api.sessions.clear()
    api.session_owners.clear()


def signup(owner, name="Sam"):
    invite = owner.post("/api/invitations", json={"label": name})
    assert invite.status_code == 201
    client = TestClient(api.app, headers=ORIGIN)
    response = client.post(
        "/api/register", json={"name": name, "invite_key": invite.json()["invite_key"]}
    )
    assert response.status_code == 201
    return client, response.json(), invite.json()


def test_registration_key_legacy_owner_and_admin_permissions(owner):
    member, account, invitation = signup(owner)
    assert len(account["access_key"]) >= 32
    text = (data_dir() / "accounts.json").read_text()
    assert account["access_key"] not in text and invitation["invite_key"] not in text
    assert account["access_key"] not in owner.get("/api/invitations").text
    for method, path in [
        ("get", "/api/invitations"),
        ("post", "/api/invitations"),
        ("delete", "/api/invitations/" + invitation["id"]),
    ]:
        assert getattr(member, method)(path).status_code == 403
    identity = member.get("/api/dashboard").json()
    assert identity["account"] == {"id": account["id"], "name": "Sam", "admin": False}
    assert identity["profile"]["name"] == "Sam"
    assert owner.get("/api/dashboard").json()["account"]["admin"]
    assert member.post("/api/logout").status_code == 200
    assert member.get("/api/dashboard").status_code == 401
    assert member.post("/api/login", json={"access_key": account["access_key"]}).status_code == 200
    assert member.get("/api/dashboard").json()["account"]["id"] == account["id"]
    assert accounts.authenticate("clé invalide") is None


def test_invitation_expiry_revocation_one_use_and_origin(owner):
    anonymous = TestClient(api.app, headers=ORIGIN)
    assert (
        anonymous.post(
            "/api/register", json={"name": "Sam", "invite_key": "unknown-key"}
        ).status_code
        == 422
    )
    assert anonymous.post("/api/invitations", json={"label": "Test"}).status_code == 401
    member, _, used = signup(owner)
    assert (
        anonymous.post(
            "/api/register", json={"name": "Sam", "invite_key": used["invite_key"]}
        ).status_code
        == 400
    )
    revoked = owner.post("/api/invitations", json={"label": "Revoked"}).json()
    assert owner.delete("/api/invitations/" + revoked["id"]).status_code == 200
    assert (
        anonymous.post(
            "/api/register", json={"name": "Sam", "invite_key": revoked["invite_key"]}
        ).status_code
        == 400
    )
    expired = owner.post("/api/invitations", json={"label": "Expired"}).json()
    with accounts.lock:
        data = accounts.registry()
        data["invitations"][accounts.fingerprint(expired["invite_key"])]["expires_at"] = (
            time.time() - 1
        )
        accounts.save(data)
    assert (
        anonymous.post(
            "/api/register", json={"name": "Sam", "invite_key": expired["invite_key"]}
        ).status_code
        == 400
    )
    assert (
        member.post(
            "/api/register", headers={"Origin": "https://untrusted.invalid"}, json={}
        ).status_code
        == 403
    )


def test_account_storage_profiles_activities_chats_memory_gym_and_secrets(owner):
    member, account, _ = signup(owner)
    db.save_profile({**db.profile(), "name": "Alex"})
    db.upsert_record("activity", "same-id", {"activityName": "Owner-only activity"})
    db.upsert_record("health", "2026-01-01", {"synthetic": "owner"})
    db.append("messages", "Owner-only conversation", "user")
    db.upsert_record(
        "gym_workout", "owner-only", {"id": "owner-only", "program_id": "p", "exercises": []}
    )
    secret = memory.edit_fact(None, "Synthetic preference", "preference", None, "active")
    write_secret(chatgpt.credential_path(), {"access_token": "synthetic-private-token"})
    before = owner.get("/api/dashboard").json()
    value = member.get("/api/dashboard").json()
    assert value["activities"] == value["health"] == value["messages"] == []
    assert not value["integrations"]["chatgpt"]["configured"]
    assert member.get("/api/gym/workouts/owner-only").status_code == 404
    assert member.delete("/api/memory/facts/" + secret["id"]).status_code == 404
    with user_scope(account["id"]):
        assert data_dir().name == account["id"]
        assert not read_secret(chatgpt.credential_path())
        db.upsert_record("activity", "same-id", {"activityName": "Member-only activity"})
        db.append("messages", "Member-only conversation", "user")
        write_secret(chatgpt.credential_path(), {"access_token": "synthetic-member-token"})
    assert owner.get("/api/dashboard").json() == before
    after = member.get("/api/dashboard").json()
    assert after["activities"][0]["data"]["activityName"] == "Member-only activity"
    assert after["messages"][0]["content"] == "Member-only conversation"
    assert "synthetic-member-token" not in str(after)
    assert "Owner-only" not in str(after)


def test_parallel_requests_and_user_context_reset(owner):
    a, first, _ = signup(owner, "Sam")
    b, second, _ = signup(owner, "Chris")

    def read(client, expected):
        for _ in range(6):
            assert client.get("/api/dashboard").json()["account"]["id"] == expected

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = [
            pool.submit(read, client, expected)
            for client, expected in [(owner, "local"), (a, first["id"]), (b, second["id"])]
        ]
        for result in results:
            result.result()
    assert user_id() == "local"
    assert not (data_dir() / "users" / "local").exists()


def test_background_workers_cancellation_and_schedule_owner(owner, monkeypatch):
    _, account, _ = signup(owner)
    seen = []
    completed = threading.Event()

    def work(job):
        seen.append(user_id())
        db.upsert_record("synthetic_job", "result", {"owner": user_id()})
        completed.set()

    monkeypatch.setattr(garmin_jobs, "work_locked", work)
    with user_scope(account["id"]):
        assert api.sync_lock.acquire(False)
        garmin_jobs.spawn({}, api.sync_lock)
    assert completed.wait(5)
    # Context propagation must retain the member after the initiating scope has exited.
    assert seen == [account["id"]]
    assert not db.record("synthetic_job", "result")
    garmin_jobs.stop.set()
    with user_scope(account["id"]):
        assert not garmin_jobs.stop.is_set()
        assert db.record("synthetic_job", "result")["owner"] == account["id"]
        api.chatgpt_login_state().update(status="awaiting", url="synthetic-member-url")
        garmin_jobs.stop.set()
    assert "url" not in api.chatgpt_login_state()
    garmin_jobs.stop.clear()
    with user_scope(account["id"]):
        assert garmin_jobs.stop.is_set()
        garmin_jobs.stop.clear()
    seen.clear()

    def tick(lock):
        seen.append(user_id())

    monkeypatch.setattr(garmin_schedule, "tick", tick)
    stopping, scheduler = garmin_schedule.start(api.sync_lock)
    try:
        deadline = time.time() + 3
        while len(seen) < 2 and time.time() < deadline:
            time.sleep(0.02)
        assert seen == ["local", account["id"]]
    finally:
        stopping.set()
        scheduler.join(3)


def test_concurrent_signup_consumes_invitation_only_once(owner):
    invitation = owner.post("/api/invitations", json={"label": "Concurrent"}).json()

    def consume():
        with TestClient(api.app, headers=ORIGIN) as client:
            return client.post(
                "/api/register", json={"name": "Sam", "invite_key": invitation["invite_key"]}
            ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert sorted(results) == [201, 400]
    assert len(accounts.registry()["users"]) == 1


def test_memory_workers_keep_context_and_do_not_share_generation_lock(owner, monkeypatch):
    _, account, _ = signup(owner)
    gate = threading.Barrier(2)
    seen = []

    def update(model):
        gate.wait(timeout=5)
        seen.append(user_id())
        db.upsert_record("synthetic_memory", "worker", {"owner": user_id()})

    monkeypatch.setattr(memory, "update", update)
    db.append("messages", "Synthetic owner message", "user")
    assert memory.launch("synthetic", force=True)
    with user_scope(account["id"]):
        db.append("messages", "Synthetic member message", "user")
        assert memory.launch("synthetic", force=True)
    deadline = time.time() + 5
    while time.time() < deadline:
        with user_scope(account["id"]):
            member_finished = db.record("memory", "job").get("status") == "completed"
        if member_finished and db.record("memory", "job").get("status") == "completed":
            break
        time.sleep(0.02)
    assert sorted(seen) == sorted(["local", account["id"]])
    assert db.record("synthetic_memory", "worker")["owner"] == "local"
    with user_scope(account["id"]):
        assert db.record("synthetic_memory", "worker")["owner"] == account["id"]
        assert not memory.generation_lock.locked()
    assert not memory.generation_lock.locked()


def test_provider_imports_use_member_scope_and_preserve_owner_sessions(owner, monkeypatch):
    from coach import garmin

    member, account, _ = signup(owner)
    owner_garmin = data_dir() / "garmin" / "garmin_tokens.json"
    write_secret(
        owner_garmin,
        {
            "di_token": "owner-token",
            "di_refresh_token": "owner-refresh",
            "di_client_id": "owner-client",
        },
    )
    write_secret(chatgpt.credential_path(), {"access_token": "owner-chatgpt"})
    seen = []

    def import_garmin(value):
        seen.append(user_id())
        write_secret(data_dir() / "garmin" / "garmin_tokens.json", value)

    def import_chatgpt(value):
        seen.append(user_id())
        write_secret(chatgpt.credential_path(), value)
        return []

    monkeypatch.setattr(garmin, "import_session", import_garmin)
    monkeypatch.setattr(chatgpt, "validate_session", lambda value: None)
    monkeypatch.setattr(chatgpt, "import_session", import_chatgpt)
    assert api.sync_lock.acquire(False)
    assert api.chat_lock.acquire(False)
    try:
        value = {
            "di_token": "member-token",
            "di_refresh_token": "member-refresh",
            "di_client_id": "member-client",
        }
        assert member.post("/api/garmin/session", json=value).status_code == 200
        assert (
            member.post("/api/chatgpt/session", json={"access_token": "member-chatgpt"}).status_code
            == 200
        )
        assert api.sync_lock.locked() and api.chat_lock.locked()
    finally:
        api.sync_lock.release()
        api.chat_lock.release()
    assert seen == [account["id"], account["id"]]
    assert read_secret(owner_garmin)["di_token"] == "owner-token"
    assert read_secret(chatgpt.credential_path())["access_token"] == "owner-chatgpt"
    assert member.post("/api/chatgpt/disconnect").status_code == 200
    assert read_secret(chatgpt.credential_path())["access_token"] == "owner-chatgpt"
    with user_scope(account["id"]):
        assert not chatgpt.credential_path().exists()
        assert (
            read_secret(data_dir() / "garmin" / "garmin_tokens.json")["di_token"] == "member-token"
        )


def test_unowned_session_never_falls_back_to_administrator(owner):
    anonymous = TestClient(api.app, headers=ORIGIN)
    anonymous.cookies.set("coach_session", "unowned-session")
    api.sessions["unowned-session"] = time.time() + 60
    assert anonymous.get("/api/invitations").status_code == 401
    assert anonymous.get("/api/dashboard").status_code == 401
    assert owner.get("/api/invitations").status_code == 200
