"""Sessions, role checks and CSRF protection."""
import hmac
import secrets
from functools import wraps

from flask import abort, current_app, g, redirect, request, session, url_for

from .db import query


def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = query(
            "SELECT id, username, is_admin, created_at FROM users WHERE id = %s", (user_id,), one=True
        )
        if g.user is None:
            session.clear()
        else:
            g.user["is_admin"] = bool(g.user["is_admin"])


def login_user(user_id: int) -> None:
    session.clear()  # prevents session fixation
    session["user_id"] = user_id
    session.permanent = True


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("auth.login", next=request.path))
        if not g.user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def csrf_token() -> str:
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def csrf_protect():
    if not current_app.config.get("CSRF_ENABLED", True):
        return
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    sent = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("_csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, description="Your form expired. Please go back, refresh the page and try again.")
