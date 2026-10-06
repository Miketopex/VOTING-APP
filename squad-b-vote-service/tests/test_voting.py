import json

from conftest import first_poll, process_queue, register


def test_demo_poll_is_seeded(app):
    poll = first_poll(app)
    assert poll["is_open"] and len(poll["options"]) == 4


def test_vote_is_queued_then_counted(app, user_client):
    poll = first_poll(app)
    option = poll["options"][1]
    resp = user_client.post(f"/polls/{poll['id']}/vote", data={"option_id": option["id"]})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/results")

    r = app.config["REDIS_CLIENT"]
    assert r.llen("votes") == 1
    msg = json.loads(r.data["votes"][0]) if hasattr(r, "data") else None
    if msg:
        assert msg["option_id"] == option["id"] and msg["poll_id"] == poll["id"]

    # Before the worker runs, the user's vote is "pending"
    assert b"in the queue" in user_client.get(f"/polls/{poll['id']}/results").data

    assert process_queue(app) == 1
    body = user_client.get(f"/api/polls/{poll['id']}/results").get_json()
    assert body["results"]["total"] == 1
    assert body["my_vote"] == "recorded"
    counted = {o["id"]: o["votes"] for o in body["results"]["options"]}
    assert counted[option["id"]] == 1


def test_one_vote_per_user_while_pending(app, user_client):
    poll = first_poll(app)
    oid = poll["options"][0]["id"]
    user_client.post(f"/polls/{poll['id']}/vote", data={"option_id": oid})
    resp = user_client.post(f"/polls/{poll['id']}/vote", data={"option_id": oid}, follow_redirects=True)
    assert b"already being counted" in resp.data
    assert app.config["REDIS_CLIENT"].llen("votes") == 1


def test_one_vote_per_user_after_counted(app, user_client):
    poll = first_poll(app)
    oid = poll["options"][0]["id"]
    user_client.post(f"/polls/{poll['id']}/vote", data={"option_id": oid})
    process_queue(app)
    resp = user_client.post(f"/polls/{poll['id']}/vote", data={"option_id": poll["options"][1]["id"]},
                            follow_redirects=True)
    assert b"already voted" in resp.data
    assert app.config["REDIS_CLIENT"].llen("votes") == 0


def test_database_constraint_blocks_duplicates(app):
    """Even if two messages reach the worker, the UNIQUE constraint keeps one vote."""
    import pytest
    from app.db import execute, utcnow

    poll = first_poll(app)
    with app.app_context():
        execute("INSERT INTO votes (poll_id, option_id, user_id, created_at) VALUES (%s, %s, %s, %s)",
                (poll["id"], poll["options"][0]["id"], 1, utcnow()))
        with pytest.raises(Exception):
            execute("INSERT INTO votes (poll_id, option_id, user_id, created_at) VALUES (%s, %s, %s, %s)",
                    (poll["id"], poll["options"][1]["id"], 1, utcnow()))


def test_many_users_results(app):
    poll = first_poll(app)
    picks = [0, 0, 1, 2, 0]
    for i, pick in enumerate(picks):
        c = app.test_client()
        register(c, f"user{i}")
        c.post(f"/polls/{poll['id']}/vote", data={"option_id": poll["options"][pick]["id"]})
    assert process_queue(app) == 5
    c = app.test_client()
    register(c, "viewer")
    res = c.get(f"/api/polls/{poll['id']}/results").get_json()["results"]
    assert res["total"] == 5
    assert [o["votes"] for o in res["options"]] == [3, 1, 1, 0]
    assert res["options"][0]["percent"] == 60.0


def test_invalid_option_rejected(app, user_client):
    poll = first_poll(app)
    resp = user_client.post(f"/polls/{poll['id']}/vote", data={"option_id": 99999}, follow_redirects=True)
    assert b"does not belong" in resp.data
    assert app.config["REDIS_CLIENT"].llen("votes") == 0


def test_missing_option_rejected(app, user_client):
    poll = first_poll(app)
    resp = user_client.post(f"/polls/{poll['id']}/vote", data={}, follow_redirects=True)
    assert b"choose an option" in resp.data


def test_closed_poll_rejects_votes(app, user_client, admin_client):
    poll = first_poll(app)
    admin_client.post(f"/admin/polls/{poll['id']}/toggle")
    resp = user_client.post(f"/polls/{poll['id']}/vote", data={"option_id": poll["options"][0]["id"]},
                            follow_redirects=True)
    assert b"closed" in resp.data


def test_unknown_poll_404(user_client):
    assert user_client.get("/polls/9999").status_code == 404
    assert user_client.get("/polls/9999/results").status_code == 404


def test_results_are_cached(app, user_client):
    poll = first_poll(app)
    url = f"/api/polls/{poll['id']}/results"
    assert user_client.get(url).get_json()["source"] == "database"
    assert user_client.get(url).get_json()["source"] == "cache"


def test_worker_invalidates_cache(app, user_client):
    poll = first_poll(app)
    url = f"/api/polls/{poll['id']}/results"
    user_client.get(url)  # warm the cache (0 votes)
    user_client.post(f"/polls/{poll['id']}/vote", data={"option_id": poll["options"][0]["id"]})
    process_queue(app)  # deletes results:{poll}
    body = user_client.get(url).get_json()
    assert body["source"] == "database" and body["results"]["total"] == 1


def test_results_fall_back_to_db_when_cache_down(app, user_client):
    r = app.config["REDIS_CLIENT"]
    if not hasattr(r, "down"):
        return  # only meaningful with the in-memory fake
    poll = first_poll(app)
    r.down = True
    resp = user_client.get(f"/polls/{poll['id']}/results")
    assert resp.status_code == 200


def test_vote_rejected_cleanly_when_redis_down(app, user_client):
    r = app.config["REDIS_CLIENT"]
    if not hasattr(r, "down"):
        return
    poll = first_poll(app)
    r.down = True
    resp = user_client.post(f"/polls/{poll['id']}/vote", data={"option_id": poll["options"][0]["id"]},
                            follow_redirects=True)
    assert resp.status_code == 200
    assert b"temporarily unavailable" in resp.data
