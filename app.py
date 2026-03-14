import os

from ssbstats_app import create_app

# This file is the entry point for local development and testing. It creates the Flask app and runs it on localhost:5000.
app = create_app()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", "5001")))
