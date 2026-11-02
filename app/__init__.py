"""The app package.

Contains the application factory, create_app(), which builds and returns
a configured Flask app.
"""

from dotenv import load_dotenv
from flask import Flask

# Load variables from .env into the environment BEFORE importing Config,
# because Config reads os.environ when its module is first imported.
load_dotenv()

from app.config import Config  # noqa: E402  (must come after load_dotenv)


def create_app(config_class: type[Config] = Config) -> Flask:
    """Create and configure a Flask application.

    Using a factory function (instead of one global ``app`` object) lets the
    tests create a fresh app with test settings every time.

    Args:
        config_class: The settings class to load. Defaults to ``Config``.

    Returns:
        A ready-to-run Flask application.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Imported here, not at the top, to avoid a circular import
    # (routes.py may later need things from this package).
    from app.routes import main_bp

    app.register_blueprint(main_bp)
    return app
