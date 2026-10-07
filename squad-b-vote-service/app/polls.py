from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import services
from .security import login_required

bp = Blueprint("polls", __name__)


@bp.route("/")
def index():
    if not g.user:
        return render_template("landing.html")
    polls = services.list_polls(include_closed=True)
    for p in polls:
        p["my_status"], _ = services.vote_status(p["id"], g.user["id"])
    return render_template("polls/index.html", polls=polls)


@bp.route("/polls/<int:poll_id>")
@login_required
def detail(poll_id):
    poll = services.get_poll(poll_id)
    if not poll:
        abort(404)
    status, recorded = services.vote_status(poll_id, g.user["id"])
    return render_template("polls/vote.html", poll=poll, status=status, recorded=recorded)


@bp.route("/polls/<int:poll_id>/vote", methods=["POST"])
@login_required
def vote(poll_id):
    try:
        services.cast_vote(g.user["id"], poll_id, request.form.get("option_id"))
    except services.VoteError as exc:
        flash(str(exc), "error")
        return redirect(url_for("polls.detail", poll_id=poll_id))
    flash("Thanks! Your vote is in the queue and will appear in the results in a moment.", "success")
    return redirect(url_for("polls.results", poll_id=poll_id))


@bp.route("/polls/<int:poll_id>/results")
@login_required
def results(poll_id):
    data, source = services.get_results(poll_id)
    if data is None:
        abort(404)
    status, recorded = services.vote_status(poll_id, g.user["id"])
    return render_template("polls/results.html", r=data, source=source, status=status, recorded=recorded)
