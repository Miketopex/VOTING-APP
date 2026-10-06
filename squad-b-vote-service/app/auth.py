from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from .security import login_user
from .services import VoteError, authenticate, register_user

bp = Blueprint("auth", __name__)


def _safe_next(target: str | None) -> str:
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("polls.index")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("polls.index"))
    if request.method == "POST":
        try:
            user_id = register_user(
                request.form.get("username", ""), request.form.get("password", ""), request.form.get("confirm", ""),
            )
        except VoteError as exc:
            flash(str(exc), "error")
            return render_template("auth/register.html", username=request.form.get("username", "")), 400
        login_user(user_id)
        flash("Welcome to CloudVote! Pick a poll and cast your vote.", "success")
        return redirect(url_for("polls.index"))
    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("polls.index"))
    if request.method == "POST":
        user = authenticate(request.form.get("username", ""), request.form.get("password", ""))
        if user is None:
            flash("Incorrect username or password.", "error")
            return render_template("auth/login.html", username=request.form.get("username", "")), 401
        login_user(user["id"])
        return redirect(_safe_next(request.args.get("next")))
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))
