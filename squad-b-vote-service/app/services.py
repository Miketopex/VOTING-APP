# flake8: noqa
# flake8: noqa
# flake8: noqa
"""Business logic for accounts, polls, voting, results and admin statistics."""
import json
import logging
import re
import time
import urllib.request
import uuid
from datetime import timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from . import cache
from .db import execute, ping, query, utcnow

log = logging.getLogger("cloudvote")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,40}$")


class VoteError(ValueError):
    """A user-facing problem (bad input, duplicate vote, closed poll …)."""

def register_user(username: str, password: str, confirm: str | None = None, is_admin: bool = False) -> int:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise VoteError("Username must be 3–40 characters: letters, numbers, dot, dash or underscore.")
    if len(password or "") < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise VoteError("Password must be at least 8 characters and contain a letter and a number.")
    if confirm is not None and password != confirm:
        raise VoteError("Passwords do not match.")
    if query("SELECT id FROM users WHERE LOWER(username) = LOWER(%s)", (username,), one=True):
        raise VoteError("That username is already taken.")
    user_id = execute(
        "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
        (username, generate_password_hash(password), is_admin, utcnow()),
        returning=True,
    )
    log.info("user_registered", extra={"user_id": user_id, "is_admin": is_admin})
    return user_id


def authenticate(username: str, password: str):
    user = query(
        "SELECT id, username, password_hash, is_admin FROM users WHERE LOWER(username) = LOWER(%s)",
        ((username or "").strip(),), one=True,
    )
    if user and check_password_hash(user["password_hash"], password or ""):
        log.info("login_success", extra={"user_id": user["id"]})
        return user
    log.warning("login_failed", extra={"username": (username or "")[:40]})
    return None


def ensure_admin() -> None:
    """Create the first administrator from ADMIN_USERNAME / ADMIN_PASSWORD."""
    username = current_app.config["ADMIN_USERNAME"]
    password = current_app.config["ADMIN_PASSWORD"]
    if not username or not password:
        return
    existing = query("SELECT id, is_admin FROM users WHERE LOWER(username) = LOWER(%s)", (username,), one=True)
    if existing is None:
        register_user(username, password, is_admin=True)
    elif not existing["is_admin"]:
        execute("UPDATE users SET is_admin = %s WHERE id = %s", (True, existing["id"]))


def seed_demo_poll() -> None:
    if not current_app.config["SEED_DEMO_POLL"]:
        return
    if query("SELECT id FROM polls LIMIT 1", one=True):
        return
    create_poll(
        "Which AWS service would you use to run a containerised app like this one?",
        ["Amazon EC2", "Amazon ECS on Fargate", "AWS Lambda", "AWS Elastic Beanstalk"],
        created_by=None,
    )



def create_poll(question: str, labels: list[str], created_by: int | None) -> int:
    question = (question or "").strip()
    labels = [lbl.strip() for lbl in labels if lbl and lbl.strip()]
    if not 5 <= len(question) <= 200:
        raise VoteError("The question must be between 5 and 200 characters.")
    if not 2 <= len(labels) <= 6:
        raise VoteError("A poll needs between 2 and 6 options.")
    if len({lbl.lower() for lbl in labels}) != len(labels):
        raise VoteError("Options must be different from each other.")
    if any(len(lbl) > 100 for lbl in labels):
        raise VoteError("Each option must be 100 characters or fewer.")
    poll_id = execute(
        "INSERT INTO polls (question, is_open, created_by, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
        (question, True, created_by, utcnow()), returning=True,
    )
    for position, label in enumerate(labels):
        execute(
            "INSERT INTO options (poll_id, label, position) VALUES (%s, %s, %s) RETURNING id",
            (poll_id, label, position), returning=True,
        )
    log.info("poll_created", extra={"poll_id": poll_id, "user_id": created_by, "options": len(labels)})
    return poll_id


def set_poll_open(poll_id: int, is_open: bool) -> bool:
    changed = execute("UPDATE polls SET is_open = %s WHERE id = %s", (is_open, poll_id))
    try:
        cache.get_redis().delete(cache.results_key(poll_id))
    except Exception:
        log.warning("cache_unavailable", extra={"poll_id": poll_id})
    log.info("poll_status_changed", extra={"poll_id": poll_id, "is_open": is_open})
    return bool(changed)


def list_polls(include_closed: bool = True):
    sql = "SELECT * FROM polls"
    params: tuple = ()
    if not include_closed:
        sql += " WHERE is_open = %s"
        params = (True,)
    rows = query(sql + " ORDER BY created_at DESC, id DESC", params)
    for r in rows:
        r["is_open"] = bool(r["is_open"])
    return rows


def get_poll(poll_id: int):
    poll = query("SELECT * FROM polls WHERE id = %s", (poll_id,), one=True)
    if not poll:
        return None
    poll["is_open"] = bool(poll["is_open"])
    poll["options"] = query(
        "SELECT id, label, position FROM options WHERE poll_id = %s ORDER BY position, id", (poll_id,)
    )
    return poll


def recorded_vote(poll_id: int, user_id: int):
    return query(
        "SELECT v.option_id, o.label, v.created_at FROM votes v JOIN options o ON o.id = v.option_id "
        "WHERE v.poll_id = %s AND v.user_id = %s", (poll_id, user_id), one=True,
    )


def vote_status(poll_id: int, user_id: int):
    """'recorded' (in the database), 'pending' (still in the queue) or None."""
    recorded = recorded_vote(poll_id, user_id)
    if recorded:
        return "recorded", recorded
    try:
        if cache.get_redis().exists(cache.pending_key(poll_id, user_id)):
            return "pending", None
    except Exception:
        log.warning("cache_unavailable", extra={"poll_id": poll_id})
    return None, None


def cast_vote(user_id: int, poll_id: int, option_id) -> None:
    """Validate a vote and put it on the Redis queue for the worker.

    One vote per user is enforced in three layers:
      1. the database already has a vote for this user  -> rejected here
      2. a vote is already waiting in the queue         -> rejected by SET NX
      3. anything that still slips through              -> UNIQUE(poll_id, user_id)
    """
    poll = get_poll(poll_id)
    if poll is None:
        raise VoteError("That poll does not exist.")
    if not poll["is_open"]:
        raise VoteError("This poll is closed.")
    try:
        option_id = int(option_id)
    except (TypeError, ValueError):
        raise VoteError("Please choose an option.")
    if option_id not in {o["id"] for o in poll["options"]}:
        raise VoteError("That option does not belong to this poll.")
    if recorded_vote(poll_id, user_id):
        raise VoteError("You have already voted in this poll.")

    r = cache.get_redis()
    pending = cache.pending_key(poll_id, user_id)
    try:
        first = r.set(pending, "1", nx=True, ex=current_app.config["PENDING_VOTE_SECONDS"])
    except Exception:
        log.error("vote_queue_unavailable", extra={"poll_id": poll_id, "user_id": user_id})
        raise VoteError("Voting is temporarily unavailable. Please try again in a minute.")
    if not first:
        raise VoteError("Your vote is already being counted.")

    message = {
        "poll_id": poll_id,
        "option_id": option_id,
        "user_id": user_id,
        "queued_at": utcnow().isoformat(),
        "request_id": uuid.uuid4().hex[:16],
        "attempts": 0,
    }
    try:
        r.lpush(cache.queue_key(), json.dumps(message))
    except Exception:
        try:
            r.delete(pending)
        except Exception:
            pass
        log.error("vote_queue_unavailable", extra={"poll_id": poll_id, "user_id": user_id})
        raise VoteError("Voting is temporarily unavailable. Please try again in a minute.")
    cache.incr("votes_queued")
    log.info("vote_queued", extra={"poll_id": poll_id, "user_id": user_id, "request_id": message["request_id"]})


def _results_from_db(poll):
    counts = {
        row["option_id"]: int(row["n"])
        for row in query(
            "SELECT option_id, COUNT(*) AS n FROM votes WHERE poll_id = %s GROUP BY option_id", (poll["id"],)
        )
    }
    total = sum(counts.values())
    options = []
    for o in poll["options"]:
        n = counts.get(o["id"], 0)
        options.append({
            "id": o["id"], "label": o["label"], "votes": n,
            "percent": round(n * 100 / total, 1) if total else 0.0,
        })
    return {
        "poll_id": poll["id"], "question": poll["question"], "is_open": poll["is_open"],
        "total": total, "options": options, "generated_at": utcnow().isoformat() + "Z",
    }


def get_results(poll_id: int):
    """Results with a Redis cache in front of PostgreSQL.

    Returns (results, source) where source is "cache" or "database".
    The worker deletes the cache key whenever a new vote is stored, so the
    cache never shows stale numbers for longer than one worker cycle.
    """
    r = cache.get_redis()
    key = cache.results_key(poll_id)
    try:
        cached = r.get(key)
    except Exception:
        cached = None
        log.warning("cache_unavailable", extra={"poll_id": poll_id})
    if cached:
        cache.incr("cache_hits")
        return json.loads(cached), "cache"

    poll = get_poll(poll_id)
    if poll is None:
        return None, None
    results = _results_from_db(poll)
    try:
        r.setex(key, current_app.config["RESULTS_CACHE_SECONDS"], json.dumps(results))
        cache.incr("cache_misses")
    except Exception:
        pass
    return results, "database"


def _check(fn):
    start = time.perf_counter()
    try:
        detail = fn()
        return {"status": "ok", "latency_ms": round((time.perf_counter() - start) * 1000, 1), **(detail or {})}
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__}


def worker_health():
    """Ask the worker's own /health endpoint; fall back to its Redis heartbeat."""
    url = current_app.config["WORKER_HEALTH_URL"]
    heartbeat = cache.get_redis().get("worker:heartbeat")
    age = round(time.time() - int(heartbeat) / 1000, 1) if heartbeat else None
    if url:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                body = json.loads(resp.read().decode())
                body["heartbeat_age_s"] = age
                return body
        except Exception as exc:
            return {"status": "error", "error": type(exc).__name__, "heartbeat_age_s": age}
    stale = age is None or age > current_app.config["WORKER_STALE_SECONDS"]
    return {"status": "error" if stale else "ok", "heartbeat_age_s": age}

def service_health():
    """Returns the live status mapping indicators for downstream ecosystem resources."""
    status = {"database": "ok", "redis": "ok", "worker": "ok"}

    try:
        from app.database import query_row
        query_row("SELECT 1")
    except Exception:
        status["database"] = "error"

    try:
        from app import cache
        cache.get_redis().ping()
    except Exception:
        status["redis"] = "error"

    try:
        import requests
        from app.config import Config
        res = requests.get(Config.WORKER_HEALTH_URL, timeout=2)
        if res.status_code != 200:
            status["worker"] = "error"
    except Exception:
        status["worker"] = "error"

    return status



def admin_stats():
    r = cache.get_redis()
    users = int(query("SELECT COUNT(*) AS n FROM users WHERE is_admin = %s", (False,), one=True)["n"])
    total_votes = int(query("SELECT COUNT(*) AS n FROM votes", one=True)["n"])
    voters = int(query("SELECT COUNT(DISTINCT user_id) AS n FROM votes", one=True)["n"])
    hits, misses = cache.stat("cache_hits"), cache.stat("cache_misses")

    since = utcnow() - timedelta(hours=24)
    buckets = {}
    for row in query("SELECT created_at FROM votes WHERE created_at >= %s", (since,)):
        hour = row["created_at"].replace(minute=0, second=0, microsecond=0)
        buckets[hour] = buckets.get(hour, 0) + 1
    start_hour = since.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    timeline = [
        {"hour": (start_hour + timedelta(hours=i)).strftime("%H:00"),
         "votes": buckets.get(start_hour + timedelta(hours=i), 0)}
        for i in range(24)
    ]

    return {
        "users": users,
        "total_votes": total_votes,
        "voters": voters,
        "participation": round(voters * 100 / users, 1) if users else 0.0,
        "queue_length": int(r.llen(cache.queue_key())),
        "failed": int(r.llen(cache.failed_key())),
        "queued_total": cache.stat("votes_queued"),
        "processed_total": cache.stat("votes_processed"),
        "duplicates": cache.stat("votes_duplicate"),
        "cache_hits": hits,
        "cache_misses": misses,
        "cache_hit_rate": round(hits * 100 / (hits + misses), 1) if (hits + misses) else 0.0,
        "timeline": timeline,
        "timeline_max": max([t["votes"] for t in timeline] + [1]),
    }
