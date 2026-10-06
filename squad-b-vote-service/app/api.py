"""JSON API.

Everything here is consumed by JavaScript, never by a browser following a link.
That one fact drives the whole module: an expired session must come back as
``401 {"error": "login_required"}``, not as a ``302`` to the HTML login page.

``security.admin_required`` redirects, which is right for a page and wrong here —
the dashboard's fetch() follows the redirect, receives a login page, tries to parse
it as JSON and dies with a syntax error that says nothing about the real problem.
So the API gets its own two decorators.
"""
import logging
import time
from functools import wraps

from flask import Blueprint, current_app, g, jsonify

from . import cache
from .health import HEARTBEAT_KEY
from .services import get_poll

bp = Blueprint("api", __name__, url_prefix="/api")
log = logging.getLogger("cloudvote.api")


def api_login_required(view):
    """401 JSON instead of a redirect."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return jsonify(error="login_required", message="Sign in to continue."), 401
        return view(*args, **kwargs)

    return wrapped


def api_admin_required(view):
    """401 if signed out, 403 if signed in without admin. Never a redirect."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return jsonify(error="login_required", message="Sign in to continue."), 401
        if not g.user["is_admin"]:
            return jsonify(error="forbidden", message="Administrators only."), 403
        return view(*args, **kwargs)

    return wrapped


@bp.get("/polls/<int:poll_id>/results")
@api_login_required
def poll_results(poll_id: int):
    poll = get_poll(poll_id)
    if poll is None:
        return jsonify(error="not_found"), 404

    options = [
        {"id": o["id"], "label": o["label"], "votes": o.get("votes", 0)}
        for o in poll.get("options", [])
    ]
    return jsonify(
        poll_id=poll["id"],
        question=poll["question"],
        is_open=bool(poll["is_open"]),
        total_votes=sum(o["votes"] for o in options),
        options=options,
    ), 200


@bp.get("/admin/stats")
@api_admin_required
def admin_stats():
    """Counters the worker keeps in Redis, plus how long ago it last ran.

    Every value degrades to 0 / unknown rather than raising: this endpoint exists to
    tell an operator what is wrong, so it has to keep answering when Redis is the
    thing that is wrong.
    """
    stats = {name: cache.stat(name) for name in ("votes_processed", "votes_duplicate", "votes_failed")}

    worker = {"alive": False, "age_seconds": None}
    queue_depth = None
    try:
        client = cache.client()
        raw = client.get(HEARTBEAT_KEY)
        if raw is not None:
            age = max(0.0, time.time() - float(raw))
            worker = {"alive": age <= current_app.config["WORKER_STALE_SECONDS"], "age_seconds": round(age, 1)}
        queue_depth = client.llen(current_app.config["VOTE_QUEUE"])
    except Exception as exc:                       # noqa: BLE001 - deliberately broad
        log.warning("admin_stats_redis_unavailable", extra={"error": str(exc)})

    return jsonify(stats=stats, worker=worker, queue_depth=queue_depth), 200
