# flake8: noqa
# flake8: noqa
import logging
import redis
from app.config import Config

log = logging.getLogger(__name__)

def get_redis():
    """Returns a thread-safe Redis client instance matching our configuration."""
    return redis.from_url(Config.REDIS_URL, decode_responses=True)

def results_key(poll_id: int) -> str:
    """Returns the formatted cache key for poll results."""
    return f"polls:{poll_id}:results"

def incr(name: str) -> int:
    """Increments a database performance counter metric metric inside our cache engine."""
    try:
        return get_redis().incr(f"stats:{name}")
    except Exception:
        log.warning("cache_unavailable", extra={"stat": name})
        return 0

def stat(name: str) -> int:
    """A counter, or 0 when Redis cannot answer."""
    try:
        value = get_redis().get(f"stats:{name}")
        return int(value) if value else 0
    except Exception:
        log.warning("cache_unavailable", extra={"stat": name})
        return 0

def pending_key(poll_id: int, user_id: int) -> str:
    """Returns the formatted cache key for a pending vote to track user actions."""
    return f"pending:{poll_id}:{user_id}"
