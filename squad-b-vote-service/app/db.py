"""Very small database layer.

Production uses PostgreSQL 16 in its own container (driver: psycopg2).
Local development and the automated tests can use SQLite so that no database
server is needed. All queries are written once with ``%s`` placeholders and
translated for SQLite automatically.
"""
import os
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import current_app, g

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(40)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_admin      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMP    NOT NULL
);

CREATE TABLE IF NOT EXISTS polls (
    id          SERIAL PRIMARY KEY,
    question    VARCHAR(200) NOT NULL,
    is_open     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by  INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMP    NOT NULL
);

CREATE TABLE IF NOT EXISTS options (
    id        SERIAL PRIMARY KEY,
    poll_id   INTEGER      NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    label     VARCHAR(100) NOT NULL,
    position  INTEGER      NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_options_poll ON options(poll_id);

-- One vote per user per poll is guaranteed by the UNIQUE constraint,
-- even if two votes somehow reach the worker.
CREATE TABLE IF NOT EXISTS votes (
    id          SERIAL PRIMARY KEY,
    poll_id     INTEGER   NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    option_id   INTEGER   NOT NULL REFERENCES options(id) ON DELETE CASCADE,
    user_id     INTEGER   NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMP NOT NULL,
    CONSTRAINT one_vote_per_user UNIQUE (poll_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_votes_poll_option ON votes(poll_id, option_id);
CREATE INDEX IF NOT EXISTS idx_votes_created ON votes(created_at);
"""

SQLITE_SCHEMA = (
    POSTGRES_SCHEMA.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    .replace("BIGINT", "INTEGER")
)


# Explicit SQLite datetime handling (Python's built-in default adapters are
# deprecated since 3.12).
sqlite3.register_adapter(datetime, lambda d: d.isoformat(" "))
sqlite3.register_converter("TIMESTAMP", lambda b: datetime.fromisoformat(b.decode()))


def utcnow() -> datetime:
    """Naive UTC timestamp (stored the same way in SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _sqlite_path(url: str) -> str:
    # sqlite:///relative/path.db  or  sqlite:////absolute/path.db  or sqlite:///:memory:
    path = url.split("sqlite:///", 1)[1]
    return path


def connect(url: str):
    if _is_sqlite(url):
        path = _sqlite_path(url)
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    import psycopg2  # imported lazily so SQLite-only environments still work
    import psycopg2.extras

    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError("DATABASE_URL must start with postgresql:// or sqlite:///")
    conn = psycopg2.connect(
        url, connect_timeout=5, cursor_factory=psycopg2.extras.RealDictCursor
    )
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_URL"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def _translate(sql: str) -> str:
    if _is_sqlite(current_app.config["DATABASE_URL"]):
        return sql.replace("%s", "?")
    return sql


def query(sql: str, params=(), one: bool = False):
    """Run a SELECT and return dict rows (or a single row / None)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_translate(sql), params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql: str, params=(), returning: bool = False):
    """Run INSERT/UPDATE/DELETE and commit. With returning=True the SQL must
    end in ``RETURNING id`` and the new id is returned."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(_translate(sql), params)
        result = None
        if returning:
            row = cur.fetchone()
            result = row["id"] if isinstance(row, dict) else row[0]
        else:
            result = cur.rowcount
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def init_schema(url: str) -> None:
    """Create tables if they do not exist (idempotent, safe on every start)."""
    conn = connect(url)
    try:
        if _is_sqlite(url):
            conn.executescript(SQLITE_SCHEMA)
        else:
            cur = conn.cursor()
            # Advisory lock: if several containers start at once only one
            # runs the DDL at a time.
            cur.execute("SELECT pg_advisory_lock(515151)")
            cur.execute(POSTGRES_SCHEMA)
            cur.execute("SELECT pg_advisory_unlock(515151)")
            cur.close()
        conn.commit()
    finally:
        conn.close()


def ping() -> None:
    """Raise if the database is unreachable (used by /health)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1")
    cur.fetchone()
    cur.close()
