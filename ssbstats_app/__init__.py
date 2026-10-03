import os
import secrets
import time
from pathlib import Path

from flask import Flask, session, url_for

from ssbstats_app.routes.api import api_bp
from ssbstats_app.routes.pages import pages_bp
from ssbstats_app.security import admin_ip_allowed


_STATIC_VERSION = str(int(time.time()))


def create_app():
    """Create and configure the Flask application instance."""
    root_dir = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=os.path.join(root_dir, "templates"),
        static_folder=os.path.join(root_dir, "static"),
    )
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        # A hard-coded fallback would let anyone forge an admin session. A random key
        # is safe; it just logs admins out whenever the process restarts.
        secret_key = secrets.token_hex(32)
        app.logger.warning("SECRET_KEY is not set; using a random per-process key.")
    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "1") == "1",
    )

    @app.template_global()
    def asset_variant(folder, name, size="sm"):
        """URL of a resized WebP copy (see scripts/maintenance/make_image_variants.py)."""
        stem = name.rsplit(".", 1)[0] if name.endswith((".png", ".jpg", ".jpeg")) else name
        return url_for("static", filename=f"assets/{folder}/{size}/{stem}.webp")

    @app.context_processor
    def inject_static_version():
        """Expose the cache-busting static asset version to templates."""
        return {
            "static_v": _STATIC_VERSION,
            "admin_ip_allowed": admin_ip_allowed(),
            "admin_logged_in": bool(session.get("is_admin")),
            "streaming_enabled": os.getenv("LOCAL_STREAMING", "0") == "1",
            # Absolute base for link-preview URLs (og:image must be absolute). Behind
            # Cloudflare the request scheme is http, so this isn't derived from the request.
            "site_url": os.getenv("SITE_URL", "https://ssbstats.app").rstrip("/"),
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
