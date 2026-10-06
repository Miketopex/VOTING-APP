"""Vote service configuration – every value comes from environment variables
so no secret is ever committed. See `.env.example`."""
import os
from datetime import timedelta
from urllib.parse import quote


def _bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _database_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if os.environ.get("POSTGRES_PASSWORD"):
        user = os.environ.get("POSTGRES_USER", "voting")
        password = quote(os.environ["POSTGRES_PASSWORD"], safe="")
        host = os.environ.get("POSTGRES_HOST", "db")
        port = os.environ.get("POSTGRES_PORT", "5432")
        name = os.environ.get("POSTGRES_DB", "voting")
        return f"postgresql://{user}:{password}@{host}:{port}/{name}"
    return "sqlite:///instance/cloudvote.db"


def _redis_url() -> str:
    if os.environ.get("REDIS_URL"):
        return os.environ["REDIS_URL"]
    host = os.environ.get("REDIS_HOST", "redis")
    port = os.environ.get("REDIS_PORT", "6379")
    password = os.environ.get("REDIS_PASSWORD")
    auth = f":{quote(password, safe='')}@" if password else ""
    return f"redis://{auth}{host}:{port}/0"


class Config:
    APP_NAME = "CloudVote"
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    APP_VERSION = os.environ.get("APP_VERSION", "dev")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    DATABASE_URL = _database_url()
    REDIS_URL = _redis_url()

    # Redis keys shared with the Node.js worker (keep in sync with worker/src/config.js)
    VOTE_QUEUE = os.environ.get("VOTE_QUEUE", "votes")
    RESULTS_CACHE_SECONDS = _int("RESULTS_CACHE_SECONDS", 10)
    PENDING_VOTE_SECONDS = _int("PENDING_VOTE_SECONDS", 600)

    WORKER_HEALTH_URL = os.environ.get("WORKER_HEALTH_URL", "http://worker:8080/health")
    WORKER_STALE_SECONDS = _int("WORKER_STALE_SECONDS", 30)

    # First administrator, created at start-up if it doesn't exist yet
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    SEED_DEMO_POLL = _bool("SEED_DEMO_POLL", True)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    # security.py marks sessions permanent; without this Flask falls back to
    # its 31-day default, which would apply to admin sessions too.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int("SESSION_HOURS", 8))
    CSRF_ENABLED = True

    REDIS_CLIENT = None  # tests inject a fake client here
    TESTING = False


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key-that-is-at-least-32-bytes-long"
    CSRF_ENABLED = False
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "Admin12345"
    SEED_DEMO_POLL = True
    WORKER_HEALTH_URL = ""
