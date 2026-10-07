"""CloudVote – vote service (Flask application factory)."""
import json
import logging
import sys
import time
import uuid

from flask import Flask, g, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .db import close_db, init_schema
from .security import csrf_protect, csrf_token, load_logged_in_user

_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line – easy to search in CloudWatch Logs Insights."""

    def format(self, record):
        entry = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "service": "vote",
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def _configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("botocore").setLevel("WARNING")
    logging.getLogger("werkzeug").setLevel("WARNING")


def _datetime(value, fmt="%d %b %Y, %H:%M") -> str:
    return value.strftime(fmt) + " UTC" if value else "—"


def create_app(config_object=Config, overrides: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)
    if overrides:
        app.config.update(overrides)

    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY environment variable is required")

    _configure_logging(app.config["LOG_LEVEL"])
    log = logging.getLogger("cloudvote")

    # Nginx sits in front of the app: trust one proxy hop for the client IP,
    # scheme (http/https) and host so generated links are correct.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    init_schema(app.config["DATABASE_URL"])

    from . import admin, api, auth, health, polls, services

    app.register_blueprint(auth.bp)
    app.register_blueprint(polls.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(health.bp)

    with app.app_context():
        services.ensure_admin()
        services.seed_demo_poll()

    app.jinja_env.filters["dt"] = _datetime
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def _before():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        g.start = time.perf_counter()
        g.user = None
        if request.blueprint != "health":
            load_logged_in_user()
        csrf_protect()

    @app.after_request
    def _after(response):
        response.headers["X-Request-ID"] = g.get("request_id", "")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.path.startswith("/health"):
            return response  # keep logs quiet – health checks run every few seconds
        user = g.get("user")
        log.info(
            "request",
            extra={
                "request_id": g.get("request_id"),
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - g.get("start", time.perf_counter())) * 1000, 1),
                "client_ip": request.remote_addr,
                "user_id": user["id"] if user else None,
            },
        )
        return response

    app.teardown_appcontext(close_db)

    def _wants_json():
        return request.path.startswith("/api/")

    @app.errorhandler(400)
    def _bad_request(err):
        if _wants_json():
            return jsonify(error="bad_request", message=err.description), 400
        return render_template("errors/error.html", code=400, message=err.description), 400

    @app.errorhandler(403)
    def _forbidden(_err):
        if _wants_json():
            return jsonify(error="forbidden"), 403
        return render_template("errors/error.html", code=403, message="This page is for administrators only."), 403

    @app.errorhandler(404)
    def _not_found(_err):
        if _wants_json():
            return jsonify(error="not_found"), 404
        return render_template("errors/error.html", code=404, message="We couldn't find that page or poll."), 404

    @app.errorhandler(500)
    def _server_error(_err):
        log.exception("unhandled_error", extra={"request_id": g.get("request_id")})
        if _wants_json():
            return jsonify(error="server_error", request_id=g.get("request_id")), 500
        return render_template(
            "errors/error.html", code=500,
            message=f"Something went wrong on our side. Reference: {g.get('request_id')}",
        ), 500

    log.info("app_started", extra={"version": app.config["APP_VERSION"]})
    return app
