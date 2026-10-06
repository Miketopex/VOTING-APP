"""Health and readiness checks.

A health endpoint that always returns 200 tells an operator nothing. This one runs a
real Postgres query and a real Redis ping, and reports **degraded** when a dependency
is gone — the app is still serving pages, but something behind it is broken and
somebody should look at it.

Three endpoints, because they answer three different questions:

* ``/health/live``  — is this process alive? No dependencies, never fails while the
  container is up. This is what a restart policy should watch; restarting the app
  because the *database* is down helps nobody.
* ``/health/ready`` — should traffic be sent here? 503 when the database is
  unreachable, because without it we cannot serve or record a vote.
* ``/health``       — the full picture for humans and dashboards.
"""
import logging
import time

from flask import Blueprint, current_app, jsonify

from . import cache
from .db import ping

bp = Blueprint("health", __name__, url_prefix="/health")
log = logging.getLogger("cloudvote.health")

# Written by the Node.js worker on every loop — keep in sync with
# squad-c-worker-data/src/config.js (heartbeatKey).
HEARTBEAT_KEY = "worker:heartbeat"


def _check_database() -> dict:
    started = time.perf_counter()
    try:
        ping()
        return {"ok": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:
        log.warning("health_database_unreachable", extra={"error": str(exc)})
        return {"ok": False, "error": type(exc).__name__}


def _check_redis() -> dict:
    started = time.perf_counter()
    try:
        cache.client().ping()
        return {"ok": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:
        log.warning("health_redis_unreachable", extra={"error": str(exc)})
        return {"ok": False, "error": type(exc).__name__}


def _check_worker() -> dict:
    """The worker writes a unix timestamp into Redis every loop. We don't call the
    worker directly — if we could reach it but Redis were broken the vote pipeline
    would still be dead, so the heartbeat is the honest signal."""
    stale_after = current_app.config["WORKER_STALE_SECONDS"]
    try:
        raw = cache.client().get(HEARTBEAT_KEY)
    except Exception as exc:
        log.warning("health_worker_unknown", extra={"error": str(exc)})
        return {"ok": False, "error": "redis_unreachable"}

    if raw is None:
        return {"ok": False, "error": "no_heartbeat"}

    try:
        age = max(0.0, time.time() - float(raw))
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_heartbeat"}

    return {"ok": age <= stale_after, "age_seconds": round(age, 1), "stale_after_seconds": stale_after}


@bp.get("/live")
def live():
    """Liveness: the process answered, so it is alive. Nothing else is checked."""
    return jsonify(status="ok", service="vote", version=current_app.config["APP_VERSION"]), 200


@bp.get("/ready")
def ready():
    """Readiness: only the database can make us unfit to serve traffic."""
    database = _check_database()
    code = 200 if database["ok"] else 503
    return jsonify(status="ok" if database["ok"] else "unavailable", database=database), code


@bp.get("")
@bp.get("/")
def health():
    checks = {"database": _check_database(), "redis": _check_redis(), "worker": _check_worker()}

    if not checks["database"]["ok"]:
        status, code = "unavailable", 503          # we cannot serve or record a vote
    elif all(c["ok"] for c in checks.values()):
        status, code = "ok", 200
    else:
        status, code = "degraded", 200             # up, but say plainly that something is wrong

    return jsonify(
        status=status,
        service="vote",
        version=current_app.config["APP_VERSION"],
        checks=checks,
    ), code
