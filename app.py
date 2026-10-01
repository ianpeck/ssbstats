import os
import threading

from ssbstats_app import create_app
from ssbstats_app.services.stats import keep_fighter_caches_warm

# Entry point for Gunicorn (app:app) and local development (python app.py, on localhost:5001).
app = create_app()


def _start_cache_warmer():
    """Keep every fighter profile pre-built in the background so pages load instantly.

    Lives here rather than in create_app() so tests don't hit the database.
    """
    threading.Thread(target=keep_fighter_caches_warm, name="cache-warmer", daemon=True).start()


if __name__ == "__main__":
    # With the debug reloader, this file runs twice; only warm in the process that serves requests.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _start_cache_warmer()
    # Bind to localhost only: the debug server lets anyone who can reach it run code.
    app.run(debug=True, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5001")))
else:
    _start_cache_warmer()
