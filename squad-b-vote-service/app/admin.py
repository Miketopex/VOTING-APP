"""Administrator dashboard — create polls, open and close them, and see whether the
vote pipeline is actually working.

The dashboard is the page you open *because* something looks wrong, so it is written
not to need Redis: if the counters cannot be read the page still renders and says so.
All logic lives in services.py; this module validates input and picks a template.
"""
import logging

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import services
from .security import admin_required

bp = Blueprint("admin", __name__, url_prefix="/admin")
log = logging.getLogger("cloudvote.admin")

MAX_QUESTION = 200
MAX_OPTION = 100


@bp.get("")
@bp.get("/")
@admin_required
def dashboard():
    stats, degraded = {}, False
    try:
        stats = services.admin_stats()
    except Exception as exc:                       # noqa: BLE001 - the page must still render
        degraded = True
        log.warning("admin_stats_unavailable", extra={"error": type(exc).__name__})

    return render_template(
        "admin/dashboard.html",
        polls=services.list_polls(),
        stats=stats,
        degraded=degraded,
    )


@bp.post("/polls")
@admin_required
def create_poll():
    question = (request.form.get("question") or "").strip()
    options = [o.strip() for o in request.form.getlist("options") if o and o.strip()]

    problem = None
    if not question:
        problem = "A poll needs a question."
    elif len(question) > MAX_QUESTION:
        problem = f"Keep the question under {MAX_QUESTION} characters."
    elif len(options) < 2:
        problem = "A poll needs at least two options — otherwise there is nothing to decide."
    elif any(len(o) > MAX_OPTION for o in options):
        problem = f"Keep each option under {MAX_OPTION} characters."
    elif len({o.lower() for o in options}) != len(options):
        problem = "Two options are the same — voters could not tell them apart."

    if problem:
        flash(problem, "error")
        return redirect(url_for("admin.dashboard"))

    try:
        poll_id = services.create_poll(question, options, g.user["id"])
    except services.VoteError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.dashboard"))

    log.info("poll_created", extra={"poll_id": poll_id, "options": len(options)})
    flash("Poll created.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.post("/polls/<int:poll_id>/toggle")
@admin_required
def toggle(poll_id: int):
    poll = services.get_poll(poll_id)
    if poll is None:
        flash("That poll no longer exists.", "error")
        return redirect(url_for("admin.dashboard"))

    opening = not poll["is_open"]
    # set_poll_open() also clears this poll's cached results — closing a poll changes
    # what voters should see, so the cached copy must not outlive the change.
    services.set_poll_open(poll_id, opening)

    log.info("poll_state_changed", extra={"poll_id": poll_id, "is_open": opening})
    flash("Poll reopened." if opening else "Poll closed — it no longer accepts votes.", "success")
    return redirect(url_for("admin.dashboard"))
