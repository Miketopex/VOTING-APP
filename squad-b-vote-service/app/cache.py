"""Redis access: the vote queue, the results cache and shared counters.

Key layout (shared with the Node.js worker – see worker/src/config.js):

    votes                      LIST   queue of pending votes (LPUSH here, BRPOP in worker)
    votes:failed               LIST   messages the worker could not process (dead-letter)
    pending:{poll}:{user}      STRING set while a user's vote waits in the queue
    results:{poll}             STRING cached JSON results (short TTL, deleted by the worker)
    worker:heartbeat           STRING epoch ms, refreshed by the worker every loop
    stats:*                    STRING counters (queued, processed, duplicate, failed,
                                       cache_hits, cache_misses)
"""
squad-b-voting-polls-Richard-Chinedu
import logging

from flask import current_app

log = logging.getLogger("cloudvote")


from flask import current_app

main

def get_redis():
    app = current_app
    client = app.extensions.get("cloudvote_redis")
    if client is None:
        client = app.config.get("REDIS_CLIENT")
        if client is None:
            import redis  # imported lazily so tests can run without the package

            client = redis.Redis.from_url(
                app.config["REDIS_URL"],
                decode_responses=True,
                socket_timeout=3,
                socket_connect_timeout=3,
                health_check_interval=30,
            )
        app.extensions["cloudvote_redis"] = client
    return client


def queue_key() -> str:
    return current_app.config["VOTE_QUEUE"]


def failed_key() -> str:
    return current_app.config["VOTE_QUEUE"] + ":failed"


def pending_key(poll_id: int, user_id: int) -> str:
    return f"pending:{poll_id}:{user_id}"


def results_key(poll_id: int) -> str:
    return f"results:{poll_id}"


def stat(name: str) -> int:
squad-b-voting-polls-Richard-Chinedu
    """A counter, or 0 when Redis cannot answer.

    These are read four times by the admin dashboard — the page you open *because*
    something looks wrong. If a counter lookup could raise, the one page that tells
    you Redis is down would be the page that breaks when Redis is down.
    """
    try:
        value = get_redis().get(f"stats:{name}")
        return int(value) if value else 0
    except Exception:  # noqa: BLE001 – cache down: report 0 rather than fail the page
        log.warning("cache_unavailable", extra={"stat": name})
        return 0


def incr(name: str) -> None:
    """Best-effort counter. A lost increment is never worth failing a request for —
    these are statistics, not votes. The vote itself is guarded separately."""
    try:
        get_redis().incr(f"stats:{name}")
    except Exception:  # noqa: BLE001 – cache down: drop the increment, keep serving
        log.warning("cache_unavailable", extra={"stat": name})

    value = get_redis().get(f"stats:{name}")
    return int(value) if value else 0


def incr(name: str) -> None:
    get_redis().incr(f"stats:{name}")
 main
