"""JSON API.

Everything here is fetched by JavaScript, never by a browser following a link.
That one fact drives the module: an expired session must come back as
``401 {"error": "login_required"}``, not as a ``302`` to the HTML login page.

``security.admin_required`` redirects, which is right for a page and wrong here —
the dashboard's fetch() follows the redirect, gets a login page, tries to parse it
as JSON and dies with a syntax error that says nothing about the real problem.
So the API gets its own two decorators.

The logic lives in services.py; this module is only routing and auth.
"""
import logging
from functools import wraps

from flask import Blueprint, g, jsonify

from . import services

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
def results(poll_id: int):
    data, source = services.get_results(poll_id)
    if data is None:
        return jsonify(error="not_found"), 404

    # The page has to tell this voter whether their own vote is counted yet.
    # "pending" means it is still in the queue, so the totals below exclude it.
    my_vote, _ = services.vote_status(poll_id, g.user["id"])
    return jsonify(results=data, source=source, my_vote=my_vote), 200


@bp.get("/admin/stats")
@api_admin_required
def admin_stats():
    """Counters for the dashboard.

    This endpoint is how an operator finds out Redis is down, so it must not be the
    thing that breaks when Redis is down. It degrades to an empty payload flagged
    ``degraded: true`` rather than returning a 500.
    """
    try:
        return jsonify(stats=services.admin_stats(), degraded=False), 200
    except Exception as exc:                       # noqa: BLE001 - must keep answering
        log.warning("admin_stats_degraded", extra={"error": type(exc).__name__})
        return jsonify(stats={}, degraded=True, error=type(exc).__name__), 200
