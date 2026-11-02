"""Tests for app/weather_service.py.

Every test MOCKS requests.get, so no test talks to the real Open-Meteo API.
`mocker` comes from the pytest-mock plugin: mocker.patch() swaps a real
object for a fake one during a single test, then puts the original back.
"""

import logging
from datetime import date, datetime

import pytest
import requests

from app.config import Config
from app.weather_service import (
    CityNotFoundError,
    CurrentWeather,
    DailyForecast,
    Location,
    WeatherAPIError,
    WeatherReport,
    WeatherServiceError,
    get_weather,
    search_cities,
)

# The exact name we patch: requests.get *as seen from inside weather_service*.
REQUESTS_GET = "app.weather_service.requests.get"

LONDON = Location(name="London", country="United Kingdom",
                  latitude=51.5, longitude=-0.12, region="England")


# ===========================================================================
# search_cities(): geocoding
# ===========================================================================

def test_search_cities_returns_locations(mocker, make_response, geocoding_response):
    """A valid city returns correctly filled Location objects."""
    mocker.patch(REQUESTS_GET, return_value=make_response(geocoding_response))

    locations = search_cities("Perth")

    assert locations == [
        Location("Perth", "Australia", -31.95224, 115.8614, "Western Australia"),
        Location("Perth", "United Kingdom", 56.39522, -3.43139, "Scotland"),
    ]


def test_search_cities_sends_correct_request(mocker, make_response, geocoding_response):
    """The right URL, parameters and timeout are sent to the API.

    The mock records how it was called, so we can inspect the request
    without sending it anywhere.
    """
    fake_get = mocker.patch(REQUESTS_GET, return_value=make_response(geocoding_response))

    search_cities("  Perth  ")

    fake_get.assert_called_once_with(
        Config.GEOCODING_URL,
        params={"name": "Perth", "count": 5, "language": "en", "format": "json"},
        timeout=Config.REQUEST_TIMEOUT,
    )


def test_search_cities_handles_missing_optional_fields(mocker, make_response):
    """A result without 'admin1' or 'country' still works (they're optional)."""
    raw = {"results": [{"name": "Atlantis", "latitude": 1, "longitude": 2}]}
    mocker.patch(REQUESTS_GET, return_value=make_response(raw))

    [location] = search_cities("Atlantis")

    assert location.region == ""
    assert location.country == ""
    assert location.display_name == "Atlantis"


# --- Negative tests -------------------------------------------------------

# NEGATIVE TEST: a city that doesn't exist must raise our own exception.
# Open-Meteo signals "no match" by leaving out the "results" key completely.
@pytest.mark.parametrize("payload", [{"generationtime_ms": 0.5}, {"results": []}])
def test_unknown_city_raises_city_not_found(mocker, make_response, payload):
    """No matches -> CityNotFoundError."""
    mocker.patch(REQUESTS_GET, return_value=make_response(payload))

    with pytest.raises(CityNotFoundError, match="xyzqwerty"):
        search_cities("xyzqwerty")


# NEGATIVE TEST: invalid input is rejected before any request is sent.
@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_empty_city_name_raises_value_error(mocker, name):
    """Empty or whitespace-only names raise ValueError and make no API call."""
    fake_get = mocker.patch(REQUESTS_GET)

    with pytest.raises(ValueError):
        search_cities(name)

    fake_get.assert_not_called()


# ===========================================================================
# Network failures -> WeatherAPIError
# ===========================================================================

# side_effect makes the mock RAISE an exception instead of returning a value.
# That's how we simulate "no internet" without unplugging anything.
@pytest.mark.parametrize(
    ("network_error", "message"),
    [
        (requests.Timeout(), "took too long"),
        (requests.ConnectionError(), "Could not connect"),
    ],
)
def test_network_problems_raise_weather_api_error(mocker, network_error, message):
    """Timeouts and connection errors become a friendly WeatherAPIError."""
    mocker.patch(REQUESTS_GET, side_effect=network_error)

    with pytest.raises(WeatherAPIError, match=message):
        search_cities("London")


def test_http_error_raises_weather_api_error_and_logs_reason(
    mocker, make_response, caplog
):
    """A 503 from the API (as really happened during development!) is handled.

    caplog is a built-in pytest fixture that captures log messages, so we can
    check the developer gets the technical reason.
    """
    reply = make_response({"error": True, "reason": "The service is overloaded"}, status=503)
    mocker.patch(REQUESTS_GET, return_value=reply)

    with caplog.at_level(logging.WARNING), pytest.raises(WeatherAPIError, match="HTTP 503"):
        get_weather(LONDON)

    assert "The service is overloaded" in caplog.text


def test_http_error_with_non_json_body_logs_raw_text(mocker, make_response, caplog):
    """If the error page is HTML (e.g. from a proxy), the raw text is logged."""
    reply = make_response(status=403, text="<html>Access denied</html>")
    reply.json.side_effect = ValueError("not JSON")
    mocker.patch(REQUESTS_GET, return_value=reply)

    with caplog.at_level(logging.WARNING), pytest.raises(WeatherAPIError, match="HTTP 403"):
        search_cities("London")

    assert "Access denied" in caplog.text


def test_http_error_without_response_is_still_handled(mocker, make_response, caplog):
    """Edge case: an HTTPError that carries no response object."""
    reply = make_response()
    reply.raise_for_status.side_effect = requests.HTTPError()  # response=None
    mocker.patch(REQUESTS_GET, return_value=reply)

    with caplog.at_level(logging.WARNING), pytest.raises(WeatherAPIError, match="HTTP"):
        search_cities("London")

    assert "no response" in caplog.text


def test_all_service_errors_share_a_base_class():
    """Routes can catch WeatherServiceError to handle every error in one place."""
    assert issubclass(CityNotFoundError, WeatherServiceError)
    assert issubclass(WeatherAPIError, WeatherServiceError)


# ===========================================================================
# Malformed / unexpected responses
# ===========================================================================

def test_invalid_json_raises_weather_api_error(mocker, make_response):
    """A body that isn't JSON at all is handled safely."""
    reply = make_response()
    reply.json.side_effect = ValueError("Expecting value")
    mocker.patch(REQUESTS_GET, return_value=reply)

    with pytest.raises(WeatherAPIError, match="invalid response"):
        search_cities("London")


@pytest.mark.parametrize("payload", [["a", "list"], "just a string", None, 42])
def test_json_that_is_not_an_object_raises_error(mocker, make_response, payload):
    """Valid JSON of the wrong type (list, string...) is rejected."""
    mocker.patch(REQUESTS_GET, return_value=make_response(payload))

    with pytest.raises(WeatherAPIError):
        search_cities("London")


def test_results_that_are_not_a_list_raise_error(mocker, make_response):
    """'results' must be a list of places."""
    mocker.patch(REQUESTS_GET, return_value=make_response({"results": "oops"}))

    with pytest.raises(WeatherAPIError):
        search_cities("London")


@pytest.mark.parametrize(
    "bad_place",
    [
        {"latitude": 1, "longitude": 2},                     # missing name
        {"name": "X", "longitude": 2},                       # missing latitude
        {"name": "X", "latitude": "north", "longitude": 2},  # latitude not a number
    ],
)
def test_incomplete_location_raises_error(mocker, make_response, bad_place):
    """A place missing required fields raises WeatherAPIError, not KeyError."""
    mocker.patch(REQUESTS_GET, return_value=make_response({"results": [bad_place]}))

    with pytest.raises(WeatherAPIError, match="incomplete location"):
        search_cities("X")


@pytest.mark.parametrize("missing_key", ["current", "daily"])
def test_forecast_missing_section_raises_error(
    mocker, make_response, forecast_response, missing_key
):
    """A forecast without its 'current' or 'daily' block is rejected."""
    del forecast_response[missing_key]
    mocker.patch(REQUESTS_GET, return_value=make_response(forecast_response))

    with pytest.raises(WeatherAPIError, match="unexpected data"):
        get_weather(LONDON)


def test_forecast_with_wrong_value_type_raises_error(
    mocker, make_response, forecast_response
):
    """A temperature that isn't a number is caught."""
    forecast_response["current"]["temperature_2m"] = "hot"
    mocker.patch(REQUESTS_GET, return_value=make_response(forecast_response))

    with pytest.raises(WeatherAPIError):
        get_weather(LONDON)


def test_daily_lists_of_different_lengths_raise_error(
    mocker, make_response, forecast_response
):
    """If one daily list is shorter, we refuse rather than silently drop a day."""
    forecast_response["daily"]["temperature_2m_min"].pop()
    mocker.patch(REQUESTS_GET, return_value=make_response(forecast_response))

    with pytest.raises(WeatherAPIError):
        get_weather(LONDON)


# ===========================================================================
# get_weather(): converting raw data into dataclasses
# ===========================================================================

def test_get_weather_builds_report(mocker, make_response, forecast_response):
    """Raw JSON is converted into a fully populated WeatherReport."""
    mocker.patch(REQUESTS_GET, return_value=make_response(forecast_response))

    report = get_weather(LONDON)

    assert isinstance(report, WeatherReport)
    assert report.location == LONDON
    assert report.temperature_unit == "°C"
    assert report.wind_unit == "km/h"
    assert report.timezone_abbreviation == "GMT"


def test_current_weather_is_converted(mocker, make_response, forecast_response):
    """Each 'current' field lands in the right CurrentWeather attribute."""
    mocker.patch(REQUESTS_GET, return_value=make_response(forecast_response))

    current = get_weather(LONDON).current

    assert isinstance(current, CurrentWeather)
    assert current.temperature == 11.8
    assert current.feels_like == 9.6
    assert current.humidity == 84
    assert current.wind_speed == 15.2
    assert current.is_day is True                 # 1 from the API -> True
    assert current.condition.description == "Light rain"
    assert current.time == datetime(2026, 11, 2, 13, 15)


def test_daily_forecast_is_converted(mocker, make_response, forecast_response):
    """The parallel daily lists become 5 DailyForecast objects, in order."""
    mocker.patch(REQUESTS_GET, return_value=make_response(forecast_response))

    daily = get_weather(LONDON).daily

    assert len(daily) == 5
    assert all(isinstance(day, DailyForecast) for day in daily)
    assert daily[0] == DailyForecast(
        date=date(2026, 11, 2),
        condition=daily[0].condition,
        temp_max=13.1,
        temp_min=8.4,
    )
    assert daily[0].day_name == "Mon"  # 2 Nov 2026 is a Monday
    assert [day.condition.description for day in daily] == [
        "Light rain", "Partly cloudy", "Clear sky", "Overcast", "Thunderstorm",
    ]


def test_night_time_uses_night_emoji(mocker, make_response, forecast_response):
    """is_day = 0 with a clear sky shows the moon."""
    forecast_response["current"]["is_day"] = 0
    forecast_response["current"]["weather_code"] = 0
    mocker.patch(REQUESTS_GET, return_value=make_response(forecast_response))

    current = get_weather(LONDON).current

    assert current.is_day is False
    assert current.condition.emoji == "🌙"


def test_get_weather_sends_coordinates_and_unit(mocker, make_response, forecast_response):
    """The location's coordinates and the chosen unit are sent to the API."""
    fake_get = mocker.patch(REQUESTS_GET, return_value=make_response(forecast_response))

    get_weather(LONDON, unit="fahrenheit")

    url = fake_get.call_args.args[0]
    params = fake_get.call_args.kwargs["params"]
    assert url == Config.FORECAST_URL
    assert params["latitude"] == 51.5
    assert params["longitude"] == -0.12
    assert params["temperature_unit"] == "fahrenheit"
    assert params["forecast_days"] == 5
    assert params["timezone"] == "auto"
    assert fake_get.call_args.kwargs["timeout"] == Config.REQUEST_TIMEOUT


def test_fahrenheit_report_uses_fahrenheit_symbol(mocker, make_response, forecast_response):
    """Asking for Fahrenheit labels the temperatures °F."""
    mocker.patch(REQUESTS_GET, return_value=make_response(forecast_response))

    assert get_weather(LONDON, unit="fahrenheit").temperature_unit == "°F"


# NEGATIVE TEST: an unsupported unit is rejected before calling the API.
@pytest.mark.parametrize("unit", ["kelvin", "Celsius", ""])
def test_invalid_unit_raises_value_error(mocker, unit):
    """Only 'celsius' and 'fahrenheit' are accepted (case-sensitive)."""
    fake_get = mocker.patch(REQUESTS_GET)

    with pytest.raises(ValueError, match="unit"):
        get_weather(LONDON, unit=unit)

    fake_get.assert_not_called()


# BOUNDARY TEST: humidity is a percentage, so 0 and 100 are its edges.
# Both edges must be accepted and stored exactly (no off-by-one, no clamping).
@pytest.mark.parametrize("humidity", [0, 100])
def test_humidity_boundaries(mocker, make_response, forecast_response, humidity):
    """The lowest (0%) and highest (100%) humidity values are kept as-is."""
    forecast_response["current"]["relative_humidity_2m"] = humidity
    mocker.patch(REQUESTS_GET, return_value=make_response(forecast_response))

    assert get_weather(LONDON).current.humidity == humidity


# BOUNDARY TEST: an empty daily block (0 days) is the smallest possible
# forecast; it should give an empty list, not crash.
def test_zero_forecast_days_gives_empty_list(mocker, make_response, forecast_response):
    """Zero days of data -> empty forecast list."""
    forecast_response["daily"] = {
        "time": [], "weather_code": [], "temperature_2m_max": [], "temperature_2m_min": [],
    }
    mocker.patch(REQUESTS_GET, return_value=make_response(forecast_response))

    assert get_weather(LONDON).daily == []


# ===========================================================================
# Location.display_name
# ===========================================================================

@pytest.mark.parametrize(
    ("location", "expected"),
    [
        (Location("Perth", "Australia", 0, 0, "Western Australia"),
         "Perth, Western Australia, Australia"),
        (Location("Monaco", "Monaco", 0, 0), "Monaco, Monaco"),
        (Location("Nowhere", "", 0, 0), "Nowhere"),
    ],
)
def test_display_name_skips_empty_parts(location: Location, expected: str) -> None:
    """Empty region/country are left out: no ', , ' in the label."""
    assert location.display_name == expected


# ===========================================================================
# The safety net itself
# ===========================================================================

def test_real_network_is_blocked_in_tests():
    """Proves the autouse fixture in conftest.py works.

    requests.get is NOT mocked here, so the call reaches the blocker
    and fails instead of contacting Open-Meteo.
    """
    with pytest.raises(RuntimeError, match="must not use the real network"):
        search_cities("London")
