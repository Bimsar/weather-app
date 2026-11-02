"""Entry point for local development.

Run with:  python run.py
(In production, Render starts the app with gunicorn instead.)
"""

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Debug mode = auto-reload on save + detailed error pages.
    # It's switched on by FLASK_DEBUG=1 in .env and must stay off in production.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
