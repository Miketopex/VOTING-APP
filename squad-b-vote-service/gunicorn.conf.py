"""Gunicorn configuration for the vote service.

Referenced by wsgi.py's docstring and by the Dockerfile's CMD.
"""
import multiprocessing
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


bind = f"0.0.0.0:{_int('PORT', 5000)}"

# Flask here is synchronous and spends its time waiting on Postgres and Redis, so
# the usual (2 x cores) + 1 applies. Capped, because each worker holds its own
# database connection and a t3.micro does not have many to give.
workers = _int("WEB_CONCURRENCY", min((multiprocessing.cpu_count() * 2) + 1, 8))
worker_class = "sync"
threads = _int("WEB_THREADS", 2)

timeout = _int("WEB_TIMEOUT", 30)
graceful_timeout = 20
keepalive = 5                 # nginx holds connections open; don't drop them early

# create_app() runs init_schema() and seeds the first admin. Preloading means that
# happens once in the master process rather than once per worker, which also avoids
# several workers racing for the same advisory lock at start-up.
preload_app = True

max_requests = 1000           # recycle workers to bound any slow leak
max_requests_jitter = 100     # ...but not all at the same moment

# The app already emits one JSON object per line (see app/__init__.py), so gunicorn
# only needs to report its own errors. Access logging is left off to avoid logging
# every request twice.
accesslog = None
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
