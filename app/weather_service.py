"""Talk to the Open-Meteo API and turn its JSON into clean Python objects.

This is the only module that knows about HTTP and Open-Meteo's JSON format.
The rest of the app works with the dataclasses defined here, so if the API
ever changes, only this file needs updating.

Flow:
    search_cities("Perth")  ->  [Location, Location, ...]
    get_weather(location)   ->  WeatherReport (current + 5-day forecast)
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import requests

from app.config import Config
from app.weather_codes import WeatherCondition, get_condition

# The only two units Open-Meteo accepts for temperature_unit.
VALID_UNITS = ("celsius", "fahrenheit")


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
# Specific exception types let routes.py show the RIGHT message to the user
# ("city not found" vs "service unavailable") with simple except blocks.

class WeatherServiceError(Exception):
    """Base class for every error raised by this module."""


class CityNotFoundError(WeatherServiceError):
    """The geocoding API found no city matching the search."""


class WeatherAPIError(WeatherServiceError):
    """The API couldn't be reached, timed out, or sent unexpected data."""


# ---------------------------------------------------------------------------
# Dataclasses: the clean data the rest of the app uses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Location:
    """A place returned by the geocoding API."""

    name: str
    country: str
    latitude: float
    longitude: float
    region: str = ""  # e.g. "Western Australia" (admin1); not always present

    @property
    def display_name(self) -> str:
        """Readable label such as 'Perth, Western Australia, Australia'.

        Empty parts are skipped so we never show ', , Australia'.
        """
        parts = [self.name, self.region, self.country]
        return ", ".join(part for part in parts if part)


@dataclass(frozen=True)
class CurrentWeather:
    """The weather right now at a location."""

    temperature: float
    feels_like: float
    humidity: int
    wind_speed: float
    condition: WeatherCondition
    is_day: bool
    time: datetime  # local time at the location of the last update


@dataclass(frozen=True)
class DailyForecast:
    """The forecast for one day."""

    date: date
    condition: WeatherCondition
    temp_max: float
    temp_min: float

    @property
    def day_name(self) -> str:
        """Short weekday name, e.g. 'Mon'."""
        return self.date.strftime("%a")


@dataclass(frozen=True)
class WeatherReport:
    """Everything the weather page needs, bundled together."""

    location: Location
    current: CurrentWeather
    daily: list[DailyForecast]
    temperature_unit: str  # "°C" or "°F"
    wind_unit: str  # e.g. "km/h"
    timezone_abbreviation: str  # e.g. "GMT"


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get_json(url: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Send a GET request and return the JSON body as a dict.

    Every network problem is converted into WeatherAPIError, so callers only
    need to handle our own exceptions, not the many from `requests`.
    (The leading underscore means "private: only used inside this module".)

    Raises:
        WeatherAPIError: on timeout, no connection, HTTP error or invalid JSON.
    """
    try:
        response = requests.get(url, params=params, timeout=timeout)
        # Turns 4xx/5xx status codes into an HTTPError exception.
        response.raise_for_status()
        data = response.json()
    except requests.Timeout as exc:
        raise WeatherAPIError("The weather service took too long to respond.") from exc
    except requests.ConnectionError as exc:
        raise WeatherAPIError("Could not connect to the weather service. "
                              "Check your internet connection.") from exc
    except requests.HTTPError as exc:
        raise WeatherAPIError("The weather service returned an error.") from exc
    except ValueError as exc:  # response.json() failed: body isn't valid JSON
        raise WeatherAPIError("The weather service sent an invalid response.") from exc

    # Valid JSON can still be the wrong shape, e.g. a list or a string.
    if not isinstance(data, dict):
        raise WeatherAPIError("The weather service sent an unexpected response.")
    return data


# ---------------------------------------------------------------------------
# Geocoding: city name -> locations
# ---------------------------------------------------------------------------

def parse_location(raw: dict[str, Any]) -> Location:
    """Convert one geocoding result dict into a Location.

    Raises:
        WeatherAPIError: if required fields are missing or have the wrong type.
    """
    try:
        return Location(
            name=str(raw["name"]),
            country=str(raw.get("country", "")),
            latitude=float(raw["latitude"]),
            longitude=float(raw["longitude"]),
            region=str(raw.get("admin1", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherAPIError("The weather service sent incomplete location data.") from exc


def search_cities(
    name: str,
    count: int = 5,
    *,
    url: str = Config.GEOCODING_URL,
    timeout: float = Config.REQUEST_TIMEOUT,
) -> list[Location]:
    """Find places matching a city name.

    Args:
        name: What the user typed, e.g. "Perth".
        count: Maximum number of matches to return.
        url: Geocoding endpoint (overridable, e.g. for tests).
        timeout: Seconds to wait before giving up.

    Returns:
        One or more matching Locations, best match first.

    Raises:
        ValueError: if name is empty (the route should check this first).
        CityNotFoundError: if no place matches.
        WeatherAPIError: if the API fails or sends bad data.
    """
    name = name.strip()
    if not name:
        raise ValueError("City name must not be empty.")

    params = {"name": name, "count": count, "language": "en", "format": "json"}
    data = _get_json(url, params, timeout)

    # Open-Meteo leaves out the "results" key entirely when nothing matches.
    results = data.get("results")
    if not results:
        raise CityNotFoundError(f"No city found matching '{name}'.")
    if not isinstance(results, list):
        raise WeatherAPIError("The weather service sent an unexpected response.")

    return [parse_location(item) for item in results]


# ---------------------------------------------------------------------------
# Forecast: location -> weather
# ---------------------------------------------------------------------------

def parse_current(raw: dict[str, Any]) -> CurrentWeather:
    """Convert the "current" block of the forecast response into CurrentWeather."""
    is_day = bool(raw["is_day"])  # the API sends 1 or 0
    return CurrentWeather(
        temperature=float(raw["temperature_2m"]),
        feels_like=float(raw["apparent_temperature"]),
        humidity=int(raw["relative_humidity_2m"]),
        wind_speed=float(raw["wind_speed_10m"]),
        condition=get_condition(int(raw["weather_code"]), is_day=is_day),
        is_day=is_day,
        # e.g. "2026-11-02T13:15" -> datetime. Already in local time (timezone=auto).
        time=datetime.fromisoformat(raw["time"]),
    )


def parse_daily(raw: dict[str, Any]) -> list[DailyForecast]:
    """Convert the "daily" block into a list of DailyForecast.

    The API sends parallel lists (all dates in one list, all max temps in
    another...). zip() walks through them together, one day at a time.
    strict=True raises ValueError if the lists have different lengths,
    instead of silently dropping days.
    """
    days = zip(
        raw["time"],
        raw["weather_code"],
        raw["temperature_2m_max"],
        raw["temperature_2m_min"],
        strict=True,
    )
    return [
        DailyForecast(
            date=date.fromisoformat(day),
            condition=get_condition(int(code)),
            temp_max=float(t_max),
            temp_min=float(t_min),
        )
        for day, code, t_max, t_min in days
    ]


def parse_forecast(data: dict[str, Any], location: Location, unit: str) -> WeatherReport:
    """Turn the full forecast JSON into a WeatherReport.

    Raises:
        WeatherAPIError: if any expected field is missing or malformed.
    """
    try:
        current_units = data.get("current_units", {})
        return WeatherReport(
            location=location,
            current=parse_current(data["current"]),
            daily=parse_daily(data["daily"]),
            temperature_unit="°F" if unit == "fahrenheit" else "°C",
            wind_unit=current_units.get("wind_speed_10m", "km/h"),
            timezone_abbreviation=data.get("timezone_abbreviation", ""),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        # One place catches every "wrong shape" problem from the parsers.
        raise WeatherAPIError("The weather service sent unexpected data.") from exc


def get_weather(
    location: Location,
    unit: str = "celsius",
    *,
    url: str = Config.FORECAST_URL,
    timeout: float = Config.REQUEST_TIMEOUT,
) -> WeatherReport:
    """Get the current weather and 5-day forecast for a location.

    Args:
        location: Where to get the weather for (from search_cities).
        unit: "celsius" or "fahrenheit".
        url: Forecast endpoint (overridable, e.g. for tests).
        timeout: Seconds to wait before giving up.

    Raises:
        ValueError: if unit isn't "celsius" or "fahrenheit".
        WeatherAPIError: if the API fails or sends bad data.
    """
    if unit not in VALID_UNITS:
        raise ValueError(f"unit must be one of {VALID_UNITS}, got {unit!r}")

    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "weather_code",
            "wind_speed_10m",
            "is_day",
        ]),
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "timezone": "auto",  # times come back in the city's local time
        "forecast_days": 5,
        "temperature_unit": unit,
    }
    data = _get_json(url, params, timeout)
    return parse_forecast(data, location, unit)


# ---------------------------------------------------------------------------
# Try it from the terminal:  python -m app.weather_service London
# ---------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover  (manual demo, not tested)
    import sys

    city = " ".join(sys.argv[1:]) or "London"
    try:
        matches = search_cities(city)
        print("Matches:")
        for place in matches:
            print("  -", place.display_name)

        report = get_weather(matches[0])
        now = report.current
        u = report.temperature_unit
        print(f"\nWeather in {report.location.display_name}")
        print(f"  {now.condition.emoji} {now.condition.description}")
        print(f"  {now.temperature}{u} (feels like {now.feels_like}{u})")
        print(f"  Humidity {now.humidity}% | Wind {now.wind_speed} {report.wind_unit}")
        print(f"  Updated {now.time:%H:%M} {report.timezone_abbreviation}")
        print("\n5-day forecast:")
        for day in report.daily:
            print(f"  {day.day_name}  {day.condition.emoji}  "
                  f"{day.temp_max}{u} / {day.temp_min}{u}")
    except WeatherServiceError as error:
        print("Error:", error)
