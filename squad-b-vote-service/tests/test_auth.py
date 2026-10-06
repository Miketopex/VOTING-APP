from datetime import timedelta

from conftest import login, register


def test_landing_page(client):
    assert b"CloudVote" in client.get("/").data


def test_register_login_logout(client):
    assert register(client).status_code == 302
    assert b"Polls" in client.get("/").data
    client.post("/logout")
    assert login(client, "alice", "wrong").status_code == 401
    assert login(client, "alice", "Passw0rd!").status_code == 302


def test_username_is_case_insensitive_unique(client):
    register(client, "Alice")
    client.post("/logout")
    resp = register(client, "alice")
    assert resp.status_code == 400
    assert b"already taken" in resp.data


def test_weak_password_rejected(client):
    resp = register(client, "bob", "short")
    assert resp.status_code == 400


def test_invalid_username_rejected(client):
    assert register(client, "a b<script>").status_code == 400


def test_pages_require_login(client):
    for path in ("/polls/1", "/polls/1/results", "/admin/"):
        resp = client.get(path)
        assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_open_redirect_blocked(client):
    register(client)
    client.post("/logout")
    resp = client.post("/login?next=https://evil.example", data={"username": "alice", "password": "Passw0rd!"})
    assert resp.headers["Location"] == "/"


def test_admin_is_bootstrapped(admin_client):
    assert admin_client.get("/admin/").status_code == 200


def test_csrf_enforced_when_enabled(app):
    app.config["CSRF_ENABLED"] = True
    resp = app.test_client().post("/login", data={"username": "x", "password": "y"})
    assert resp.status_code == 400


def test_session_lifetime_is_bounded(app):
    """Sessions are permanent (security.py), so the lifetime must be set explicitly.

    Without PERMANENT_SESSION_LIFETIME, Flask defaults to 31 days.
    """
    lifetime = app.config["PERMANENT_SESSION_LIFETIME"]
    assert lifetime.total_seconds() > 0
    assert lifetime <= timedelta(hours=24)
