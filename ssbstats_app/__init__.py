import os
import time
from pathlib import Path

from flask import Flask, request, session

from ssbstats_app.routes.api import api_bp
from ssbstats_app.routes.pages import pages_bp


_STATIC_VERSION = str(int(time.time()))


def create_app():
    """Create and configure the Flask application instance."""
    root_dir = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=os.path.join(root_dir, "templates"),
        static_folder=os.path.join(root_dir, "static"),
    )
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "local-dev-secret-change-me")

    @app.context_processor
    def inject_static_version():
        """Expose the cache-busting static asset version to templates."""
        raw = (os.getenv("ADMIN_ALLOWED_IPS") or "").strip()
        request_ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or ""
        admin_ip_allowed = request_ip in {"127.0.0.1", "::1", "localhost"}
        if not admin_ip_allowed:
            if not raw:
                admin_ip_allowed = True
            else:
                allowed = {ip.strip() for ip in raw.split(",") if ip.strip()}
                admin_ip_allowed = request_ip in allowed
        return {
            "static_v": _STATIC_VERSION,
            "admin_ip_allowed": admin_ip_allowed,
            "admin_logged_in": bool(session.get("is_admin")),
            "streaming_enabled": os.getenv("LOCAL_STREAMING", "0") == "1",
        }

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)

    if os.getenv("LOCAL_STREAMING", "0") == "1":
        # Local-only Gamecast — never registered in production.
        from ssbstats_app.streaming.gamecast import gamecast_bp
        app.register_blueprint(gamecast_bp)

        try:
            from streaming_jobs.kafka_io import ensure_topics
            ensure_topics()
        except Exception as exc:  # noqa: BLE001
            # Kafka may not be up yet when the app boots - the per-request
            # producer call will surface a clearer error to the user.
            print(f"[gamecast] ensure_topics() failed at startup: {exc}")

    return app
