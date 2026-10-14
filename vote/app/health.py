"""Health and readiness checks.

A health endpoint that always returns 200 tells an operator nothing. The real checks
live in ``services.service_health()`` — a genuine Postgres query, a genuine Redis
ping and the worker's heartbeat age. This module only decides what HTTP status each
outcome deserves, which is a routing decision rather than business logic.

Three endpoints, because they answer three different questions:

* ``/health/live``  — is this process alive? No dependencies, so a restart policy
  never kills the app because the *database* is down. Restarting would not help.
* ``/health/ready`` — should traffic come here? 503 when the database is gone,
  because without it we can neither serve nor record a vote.
* ``/health``       — the full picture, for dashboards and for humans.
"""
import logging

from flask import Blueprint, current_app, jsonify

from . import services

bp = Blueprint("health", __name__, url_prefix="/health")
log = logging.getLogger("cloudvote.health")


def _ok(check) -> bool:
    return isinstance(check, dict) and check.get("status") == "ok"


@bp.get("/live")
def live():
    """Liveness: we answered, so we are alive. Nothing else is checked."""
    return jsonify(status="ok", service="vote", version=current_app.config["APP_VERSION"]), 200


@bp.get("/ready")
def ready():
    """Readiness: only the database can make us unfit to serve traffic."""
    try:
        database = services.service_health()["database"]
    except Exception as exc:                       # noqa: BLE001
        log.warning("readiness_check_failed", extra={"error": type(exc).__name__})
        return jsonify(status="unavailable", error=type(exc).__name__), 503

    healthy = _ok(database)
    return jsonify(status="ok" if healthy else "unavailable", database=database), 200 if healthy else 503


@bp.get("")
@bp.get("/")
def health():
    try:
        checks = services.service_health()
    except Exception as exc:                       # noqa: BLE001
        log.exception("health_check_failed")
        return jsonify(status="unavailable", service="vote", error=type(exc).__name__), 503

    if not _ok(checks.get("database")):
        status, code = "unavailable", 503          # cannot serve or record a vote
    elif all(_ok(c) for key, c in checks.items() if key != "vote"):
        status, code = "ok", 200
    else:
        status, code = "degraded", 200             # up, but say plainly something is wrong

    return jsonify(
        status=status,
        service="vote",
        version=current_app.config["APP_VERSION"],
        checks=checks,
    ), code
