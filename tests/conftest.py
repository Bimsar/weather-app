"""Shared pytest fixtures.

pytest automatically loads this file and makes every fixture here available
to every test file, without importing anything.

A fixture is a function that prepares something a test needs (an app,
sample data, a fake object). A test asks for it simply by naming it as a
parameter, e.g. `def test_x(client): ...`.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests
from flask import Flask
from flask.testing import FlaskClient

from app import create_app
from app.config import TestingConfig


# ---------------------------------------------------------------------------
# Safety net: tests must NEVER reach the real internet
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any real HTTP request fail loudly.

    autouse=True applies this to every test automatically. If a test forgets
    to mock requests.get, it fails with a clear message instead of silently
    calling Open-Meteo (which would make tests slow and unreliable; we saw
    the API return 503 errors while building this project).
    """
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Tests must not use the real network: mock requests.get")

    monkeypatch.setattr(requests.Session, "send", refuse)


# ---------------------------------------------------------------------------
# Flask app fixtures (used by the route tests in Stage 11)
# ---------------------------------------------------------------------------

@pytest.fixture
def app() -> Flask:
    """A fresh Flask app using test settings."""
    return create_app(TestingConfig)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """A test client: a fake browser that sends requests to the app."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Sample API responses (copied from the shape Open-Meteo really returns)
# ---------------------------------------------------------------------------

@pytest.fixture
def geocoding_response() -> dict[str, Any]:
    """Geocoding API reply with two cities called Perth."""
    return {
        "results": [
            {
                "id": 2063523,
                "name": "Perth",
                "latitude": -31.95224,
                "longitude": 115.8614,
                "country": "Australia",
                "admin1": "Western Australia",
                "timezone": "Australia/Perth",
            },
            {
                "id": 2640354,
                "name": "Perth",
                "latitude": 56.39522,
                "longitude": -3.43139,
                "country": "United Kingdom",
                "admin1": "Scotland",
                "timezone": "Europe/London",
            },
        ],
        "generationtime_ms": 0.9,
    }


@pytest.fixture
def forecast_response() -> dict[str, Any]:
    """Forecast API reply: current weather + 5 days (Celsius, daytime)."""
    return {
        "latitude": 51.5,
        "longitude": -0.12,
        "timezone": "Europe/London",
        "timezone_abbreviation": "GMT",
        "current_units": {
            "temperature_2m": "°C",
            "wind_speed_10m": "km/h",
        },
        "current": {
            "time": "2026-11-02T13:15",
            "interval": 900,
            "temperature_2m": 11.8,
            "apparent_temperature": 9.6,
            "relative_humidity_2m": 84,
            "weather_code": 61,
            "wind_speed_10m": 15.2,
            "is_day": 1,
        },
        "daily": {
            "time": ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"],
            "weather_code": [61, 2, 0, 3, 95],
            "temperature_2m_max": [13.1, 12.0, 14.5, 11.2, 10.0],
            "temperature_2m_min": [8.4, 6.9, 7.1, 5.5, 4.8],
        },
    }


# ---------------------------------------------------------------------------
# Fake HTTP responses
# ---------------------------------------------------------------------------

@pytest.fixture
def make_response() -> Callable[..., MagicMock]:
    """Factory fixture: build a fake `requests.Response`.

    It returns a function (not a response) so each test can build exactly
    the response it needs, e.g. make_response(json_data={...}, status=503).
    """
    def _make(json_data: Any = None, status: int = 200, text: str = "") -> MagicMock:
        response = MagicMock(spec=requests.Response)
        response.status_code = status
        response.text = text
        response.json.return_value = json_data
        if status >= 400:
            # Behave like the real raise_for_status() does for error codes.
            response.raise_for_status.side_effect = requests.HTTPError(response=response)
        return response

    return _make
