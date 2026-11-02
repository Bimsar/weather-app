"""Application settings.

All configuration lives here so that nothing (URLs, timeouts, secrets) is
hard-coded inside functions. Values that differ between computers, or that
must stay secret, are read from environment variables.
"""

import os


class Config:
    """Default settings used when running the app normally."""

    # SECRET_KEY signs the session cookie (recent searches, °C/°F choice).
    # It comes from the environment so the real key is never committed to Git.
    # The fallback only exists so the app still starts on a fresh clone;
    # it must never be used in production.
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-only-insecure-key")

    # Open-Meteo endpoints (free, no API key needed).
    GEOCODING_URL: str = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST_URL: str = "https://api.open-meteo.com/v1/forecast"

    # Never wait forever for the API: without a timeout a slow network
    # would freeze the page for the user.
    REQUEST_TIMEOUT: int = 10

    TESTING: bool = False


class TestingConfig(Config):
    """Settings used by pytest."""

    TESTING = True
    SECRET_KEY = "test-secret-key"
