import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402

# CI also runs this suite against real PostgreSQL + Redis service containers:
#   TEST_DATABASE_URL=postgresql://…  TEST_REDIS_URL=redis://…
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL")


class FakeRedis:
    """In-memory stand-in for the subset of redis-py that the app uses."""

    def __init__(self):
        self.data, self.expiry, self.down = {}, {}, False

    def _check(self):
        if self.down:
            raise ConnectionError("redis is down")

    def _alive(self, key):
        exp = self.expiry.get(key)
        if exp is not None and exp < time.time():
            self.data.pop(key, None)
            self.expiry.pop(key, None)
        return key in self.data

    def ping(self):
        self._check()
        return True

    def get(self, key):
        self._check()
        return self.data.get(key) if self._alive(key) else None

    def set(self, key, value, nx=False, ex=None):
        self._check()
        if nx and self._alive(key):
            return None
        self.data[key] = str(value)
        if ex:
            self.expiry[key] = time.time() + ex
        return True

    def setex(self, key, seconds, value):
        return self.set(key, value, ex=seconds)

    def delete(self, *keys):
        self._check()
        n = 0
        for k in keys:
            n += 1 if self.data.pop(k, None) is not None else 0
            self.expiry.pop(k, None)
        return n

    def exists(self, key):
        self._check()
        return 1 if self._alive(key) else 0

    def incr(self, key):
        self._check()
        self.data[key] = str(int(self.data.get(key, 0)) + 1)
        return int(self.data[key])

    def lpush(self, key, *values):
        self._check()
        lst = self.data.setdefault(key, [])
        for v in values:
            lst.insert(0, v)
        return len(lst)

    def rpop(self, key):
        self._check()
        lst = self.data.get(key) or []
        return lst.pop() if lst else None

    def llen(self, key):
        self._check()
        return len(self.data.get(key) or [])

    def flushdb(self):
        self.data.clear()
        self.expiry.clear()


def _reset_postgres(url):
    from app.db import connect

    conn = connect(url)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS votes, options, polls, users CASCADE")
    conn.commit()
    conn.close()


@pytest.fixture
def redis_client():
    if TEST_REDIS_URL:
        import redis

        client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
        client.flushdb()
        return client
    return FakeRedis()


@pytest.fixture
def app(tmp_path, redis_client):
    if TEST_DATABASE_URL:
        _reset_postgres(TEST_DATABASE_URL)
        db_url = TEST_DATABASE_URL
    else:
        db_url = f"sqlite:///{tmp_path / 'test.db'}"
    return create_app(TestConfig, {"DATABASE_URL": db_url, "REDIS_CLIENT": redis_client})


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, username="alice", password="Passw0rd!"):
    return client.post("/register", data={"username": username, "password": password, "confirm": password})


def login(client, username, password):
    return client.post("/login", data={"username": username, "password": password})


def process_queue(app):
    """Test double for the Node.js worker: drain the queue with the same SQL
    (INSERT … ON CONFLICT DO NOTHING) and the same cache invalidation."""
    from app.db import execute, query

    r = app.config["REDIS_CLIENT"]
    processed = 0
    with app.app_context():
        while True:
            raw = r.rpop(app.config["VOTE_QUEUE"])
            if raw is None:
                break
            msg = json.loads(raw)
            existing = query("SELECT id FROM votes WHERE poll_id = %s AND user_id = %s",
                             (msg["poll_id"], msg["user_id"]), one=True)
            if existing:
                r.incr("stats:votes_duplicate")
            else:
                execute(
                    "INSERT INTO votes (poll_id, option_id, user_id, created_at) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (poll_id, user_id) DO NOTHING",
                    (msg["poll_id"], msg["option_id"], msg["user_id"], msg["queued_at"].replace("T", " ")[:19]),
                )
                r.incr("stats:votes_processed")
            r.delete(f"results:{msg['poll_id']}", f"pending:{msg['poll_id']}:{msg['user_id']}")
            processed += 1
    return processed


def first_poll(app):
    from app.services import get_poll, list_polls

    with app.app_context():
        return get_poll(list_polls()[-1]["id"])


@pytest.fixture
def user_client(client):
    assert register(client).status_code == 302
    return client


@pytest.fixture
def admin_client(app):
    c = app.test_client()
    assert login(c, "admin", "Admin12345").status_code == 302
    return c
