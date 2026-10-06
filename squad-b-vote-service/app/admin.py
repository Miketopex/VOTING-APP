"""Administrator dashboard — create polls, open and close them, and see whether
the vote pipeline is actually working.

The dashboard is the page you open *because* something looks wrong, so it is written
not to need Redis: every counter falls back to 0 and the page still renders. The
numbers it shows come from the worker, not from this service, so they are the
honest view of what has been processed rather than what has been submitted.
"""
import logging
import time

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from . import cache
from .db import execute, utcnow
from .health import HEARTBEAT_KEY
from .security import admin_required
from .services import get_poll, list_polls

bp = Blueprint("admin", __name__, url_prefix="/admin")
log = logging.getLogger("cloudvote.admin")

MAX_QUESTION = 200
MAX_OPTION = 100


def _pipeline_status() -> dict:
    """Worker liveness and queue depth, or 'unknown' if Redis cannot answer."""
    status = {"worker_alive": False, "worker_age": None, "queue_depth": None, "redis_ok": False}
    try:
        client = cache.client()
        client.ping()
        status["redis_ok"] = True
        raw = client.get(HEARTBEAT_KEY)
        if raw is not None:
            age = max(0.0, time.time() - float(raw))
            status["worker_age"] = round(age, 1)
            status["worker_alive"] = age <= current_app.config["WORKER_STALE_SECONDS"]
        status["queue_depth"] = client.llen(current_app.config["VOTE_QUEUE"])
    except Exception as exc:                       # noqa: BLE001 - the dashboard must still render
        log.warning("admin_pipeline_unknown", extra={"error": str(exc)})
    return status


@bp.get("")
@bp.get("/")
@admin_required
def dashboard():
    # cache.stat() returns 0 when Redis is unreachable, so these four calls cannot
    # take the page down — that is the whole point of this dashboard existing.
    stats = {name: cache.stat(name) for name in ("votes_processed", "votes_duplicate", "votes_failed")}
    return render_template(
        "admin/dashboard.html",
        polls=list_polls(),
        stats=stats,
        pipeline=_pipeline_status(),
    )


@bp.post("/polls")
@admin_required
def create_poll():
    question = (request.form.get("question") or "").strip()
    options = [o.strip() for o in request.form.getlist("options") if o and o.strip()]

    if not question:
        flash("A poll needs a question.", "error")
        return redirect(url_for("admin.dashboard"))
    if len(question) > MAX_QUESTION:
        flash(f"Keep the question under {MAX_QUESTION} characters.", "error")
        return redirect(url_for("admin.dashboard"))
    if len(options) < 2:
        flash("A poll needs at least two options — otherwise there is nothing to decide.", "error")
        return redirect(url_for("admin.dashboard"))
    if any(len(o) > MAX_OPTION for o in options):
        flash(f"Keep each option under {MAX_OPTION} characters.", "error")
        return redirect(url_for("admin.dashboard"))
    if len({o.lower() for o in options}) != len(options):
        flash("Two options are the same — voters could not tell them apart.", "error")
        return redirect(url_for("admin.dashboard"))

    poll_id = execute(
        "INSERT INTO polls (question, is_open, created_by, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
        (question, True, g.user["id"], utcnow()),
        returning=True,
    )
    for position, label in enumerate(options):
        execute(
            "INSERT INTO options (poll_id, label, position) VALUES (%s, %s, %s)",
            (poll_id, label, position),
        )

    log.info("poll_created", extra={"poll_id": poll_id, "options": len(options)})
    flash("Poll created.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/polls/<int:poll_id>/state")
@admin_required
def set_state(poll_id: int):
    poll = get_poll(poll_id)
    if poll is None:
        flash("That poll no longer exists.", "error")
        return redirect(url_for("admin.dashboard"))

    opening = request.form.get("state") == "open"
    execute("UPDATE polls SET is_open = %s WHERE id = %s", (opening, poll_id))

    # Results are cached per poll; closing a poll changes what voters should see,
    # so drop the cached copy rather than wait for it to expire.
    try:
        cache.client().delete(f"results:{poll_id}")
    except Exception as exc:                       # noqa: BLE001
        log.warning("admin_cache_clear_failed", extra={"poll_id": poll_id, "error": str(exc)})

    log.info("poll_state_changed", extra={"poll_id": poll_id, "is_open": opening})
    flash("Poll reopened." if opening else "Poll closed.", "success")
    return redirect(url_for("admin.dashboard"))
