import os
import time
from pathlib import Path

from flask import Flask

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

    @app.context_processor
    def inject_static_version():
        """Expose the cache-busting static asset version to templates."""
        return {"static_v": _STATIC_VERSION}

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    return app
