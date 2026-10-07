import json
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from coach.config import data_dir, user_id

# Versioned initial schema. Future changes belong in an explicit migration.
SCHEMA = [
    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS profiles (user_id TEXT PRIMARY KEY, data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS records (user_id TEXT NOT NULL, kind TEXT NOT NULL, "
    "record_key TEXT NOT NULL, data TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "PRIMARY KEY (user_id, kind, record_key))",
    "CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "user_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "user_id TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    engine = create_engine(f"sqlite:///{data_dir() / 'coach.db'}", connect_args={"timeout": 20})
    try:
        with engine.begin() as conn:
            for statement in SCHEMA:
                conn.execute(text(statement))
            conn.execute(text("INSERT OR IGNORE INTO schema_version VALUES (1)"))
            if not conn.execute(text("SELECT 1 FROM schema_version WHERE version=2")).first():
                migrate_search(conn)
            yield conn
    finally:
        engine.dispose()


def profile() -> dict:
    with connection() as conn:
        row = conn.execute(
            text("SELECT data FROM profiles WHERE user_id=:u"), {"u": user_id()}
        ).first()
    return (
        json.loads(row[0])
        if row
        else {
            "name": "",
            "timezone": "Europe/Paris",
            "goals": "",
            "constraints": "",
            "sports": ["Course", "Tennis", "Musculation", "Vélo"],
        }
    )


def save_profile(value: dict):
    with connection() as conn:
        conn.execute(
            text(
                "INSERT INTO profiles VALUES (:u,:d) ON CONFLICT(user_id) "
                "DO UPDATE SET data=excluded.data"
            ),
            {"u": user_id(), "d": json.dumps(value, ensure_ascii=False)},
        )


def upsert_record(kind: str, key: str, value: dict):
    with connection() as conn:
        conn.execute(
            text(
                "INSERT INTO records VALUES (:u,:k,:r,:d,:t) "
                "ON CONFLICT(user_id,kind,record_key) DO UPDATE SET "
                "data=excluded.data, updated_at=excluded.updated_at"
            ),
            {"u": user_id(), "k": kind, "r": key, "d": json.dumps(value), "t": now()},
        )


def records(kind: str, limit: int = 30) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            text(
                "SELECT record_key,data,updated_at FROM records "
                "WHERE user_id=:u AND kind=:k ORDER BY record_key DESC LIMIT :l"
            ),
            {"u": user_id(), "k": kind, "l": limit},
        ).all()
    return [{"key": r[0], "data": json.loads(r[1]), "updated_at": r[2]} for r in rows]


def record(kind: str, key: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            text("SELECT data FROM records WHERE user_id=:u AND kind=:k AND record_key=:r"),
            {"u": user_id(), "k": kind, "r": key},
        ).first()
    return json.loads(row[0]) if row else {}


def coverage(kind: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*), MIN(record_key), MAX(record_key) FROM records "
                "WHERE user_id=:u AND kind=:k"
            ),
            {"u": user_id(), "k": kind},
        ).first()
    return {"count": row[0], "first": row[1], "last": row[2]}


def activity_page(offset: int, limit: int) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            text(
                "SELECT record_key,data,updated_at FROM records WHERE user_id=:u AND kind='activity' "
                "ORDER BY COALESCE(json_extract(data,'$.startTimeLocal'), "
                "json_extract(data,'$.startTimeGMT'), '') DESC, record_key DESC LIMIT :l OFFSET :o"
            ),
            {"u": user_id(), "l": limit, "o": offset},
        ).all()
    return [{"key": r[0], "data": json.loads(r[1]), "updated_at": r[2]} for r in rows]


def activity_months() -> list[dict]:
    with connection() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT substr(COALESCE(json_extract(data,'$.startTimeLocal'), "
                    "json_extract(data,'$.startTimeGMT')),1,7) AS month, "
                    "json_extract(data,'$.activityType.typeKey') AS sport, COUNT(*) AS activities, "
                    "SUM(json_extract(data,'$.duration')) AS duration_seconds, "
                    "SUM(json_extract(data,'$.distance')) AS distance_meters "
                    "FROM records WHERE user_id=:u AND kind='activity' GROUP BY month,sport "
                    "ORDER BY month DESC, sport LIMIT 120"
                ),
                {"u": user_id()},
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


def append(table: str, content: str, role: str | None = None):
    if table not in {"messages", "notes"}:
        raise ValueError("Unknown table")
    params = {"u": user_id(), "c": content, "t": now()}
    with connection() as conn:
        if table == "messages":
            params["r"] = role
            conn.execute(
                text("INSERT INTO messages(user_id,role,content,created_at) VALUES (:u,:r,:c,:t)"),
                params,
            )
        else:
            conn.execute(
                text("INSERT INTO notes(user_id,content,created_at) VALUES (:u,:c,:t)"), params
            )


def history(table: str, limit: int = 40) -> list[dict]:
    if table not in {"messages", "notes"}:
        raise ValueError("Unknown table")
    with connection() as conn:
        rows = conn.execute(
            text(f"SELECT * FROM {table} WHERE user_id=:u ORDER BY id DESC LIMIT :l"),
            {"u": user_id(), "l": limit},
        ).mappings()
        return list(reversed([dict(r) for r in rows]))


def migrate_search(conn):
    conn.execute(
        text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS message_search USING "
            "fts5(content, user_id UNINDEXED, message_id UNINDEXED, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO message_search(content,user_id,message_id) "
            "SELECT content,user_id,id FROM messages"
        )
    )
    conn.execute(
        text(
            "CREATE TRIGGER IF NOT EXISTS message_search_insert AFTER INSERT ON messages "
            "BEGIN INSERT INTO message_search(content,user_id,message_id) "
            "VALUES (new.content,new.user_id,new.id); END"
        )
    )
    conn.execute(
        text(
            "CREATE TRIGGER IF NOT EXISTS message_search_delete AFTER DELETE ON messages "
            "BEGIN DELETE FROM message_search WHERE message_id=old.id; END"
        )
    )
    conn.execute(
        text(
            "CREATE TRIGGER IF NOT EXISTS message_search_update AFTER UPDATE ON messages "
            "BEGIN DELETE FROM message_search WHERE message_id=old.id; "
            "INSERT INTO message_search(content,user_id,message_id) "
            "VALUES (new.content,new.user_id,new.id); END"
        )
    )
    conn.execute(text("INSERT INTO schema_version VALUES (2)"))


def messages_after(after: int, limit=30) -> list[dict]:
    with connection() as conn:
        rows = (
            conn.execute(
                text("SELECT * FROM messages WHERE user_id=:u AND id>:a ORDER BY id LIMIT :l"),
                {"u": user_id(), "a": after, "l": limit},
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


def search_messages(query: str, excluded: set[int], limit=6) -> list[dict]:
    with connection() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT m.*, snippet(message_search,0,'','','…',120) AS excerpt "
                    "FROM message_search s JOIN messages m "
                    "ON m.id=s.message_id WHERE message_search MATCH :q "
                    "AND m.user_id=:u ORDER BY bm25(message_search) LIMIT 80"
                ),
                {"u": user_id(), "q": query},
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows if r["id"] not in excluded][:limit]


def delete_record(kind: str, key: str):
    with connection() as conn:
        conn.execute(
            text("DELETE FROM records WHERE user_id=:u AND kind=:k AND record_key=:r"),
            {"u": user_id(), "k": kind, "r": key},
        )


def period_activities(start: str | None, end: str | None, sports: list[str]) -> dict:
    clauses = ["user_id=:u", "kind='activity'"]
    params = {"u": user_id()}
    day = "substr(COALESCE(json_extract(data,'$.startTimeLocal'),json_extract(data,'$.startTimeGMT')),1,10)"
    if start:
        clauses.append(day + ">=:start")
        params["start"] = start
    if end:
        clauses.append(day + "<=:end")
        params["end"] = end
    if sports:
        parts = []
        for i, sport in enumerate(sports):
            parts.append(f"json_extract(data,'$.activityType.typeKey') LIKE :s{i}")
            params[f"s{i}"] = "%" + sport + "%"
        clauses.append("(" + " OR ".join(parts) + ")")
    where = " AND ".join(clauses)
    with connection() as conn:
        total = (
            conn.execute(
                text(
                    "SELECT COUNT(*) AS count, "
                    "SUM(json_extract(data,'$.duration')) AS duration_seconds, "
                    "SUM(json_extract(data,'$.distance')) AS distance_meters "
                    "FROM records WHERE " + where
                ),
                params,
            )
            .mappings()
            .first()
        )
        rows = conn.execute(
            text(
                "SELECT record_key,data,updated_at FROM records WHERE "
                + where
                + " ORDER BY "
                + day
                + " DESC, record_key DESC LIMIT 30"
            ),
            params,
        ).all()
    return {
        "start": start,
        "end": end,
        "sports": sports,
        "totals": dict(total),
        "items": [{"key": r[0], "data": json.loads(r[1]), "updated_at": r[2]} for r in rows],
    }
