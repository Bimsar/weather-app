"""Convert WMO weather codes into readable text and emojis.

Open-Meteo describes the weather with a number called a WMO weather code
(e.g. 61 means "Slight rain"). Users don't understand numbers, so this module
translates each code into a description and an emoji.

Full list of codes: https://open-meteo.com/en/docs (section "WMO Weather
interpretation codes").
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WeatherCondition:
    """A human-friendly weather condition.

    ``frozen=True`` makes instances read-only, so a shared condition can't be
    changed by accident somewhere else in the app.
    """

    description: str
    emoji: str


# One entry per WMO code that Open-Meteo can return.
# Kept as data (a dictionary) instead of a long if/elif chain: it's easier to
# read, and adding a code is a one-line change.
WMO_CODES: dict[int, WeatherCondition] = {
    0: WeatherCondition("Clear sky", "☀️"),
    1: WeatherCondition("Mainly clear", "🌤️"),
    2: WeatherCondition("Partly cloudy", "⛅"),
    3: WeatherCondition("Overcast", "☁️"),
    45: WeatherCondition("Fog", "🌫️"),
    48: WeatherCondition("Freezing fog", "🌫️"),
    51: WeatherCondition("Light drizzle", "🌦️"),
    53: WeatherCondition("Moderate drizzle", "🌦️"),
    55: WeatherCondition("Dense drizzle", "🌧️"),
    56: WeatherCondition("Light freezing drizzle", "🌧️"),
    57: WeatherCondition("Dense freezing drizzle", "🌧️"),
    61: WeatherCondition("Light rain", "🌧️"),
    63: WeatherCondition("Moderate rain", "🌧️"),
    65: WeatherCondition("Heavy rain", "🌧️"),
    66: WeatherCondition("Light freezing rain", "🌧️"),
    67: WeatherCondition("Heavy freezing rain", "🌧️"),
    71: WeatherCondition("Light snow", "🌨️"),
    73: WeatherCondition("Moderate snow", "🌨️"),
    75: WeatherCondition("Heavy snow", "❄️"),
    77: WeatherCondition("Snow grains", "🌨️"),
    80: WeatherCondition("Light rain showers", "🌦️"),
    81: WeatherCondition("Moderate rain showers", "🌧️"),
    82: WeatherCondition("Violent rain showers", "⛈️"),
    85: WeatherCondition("Light snow showers", "🌨️"),
    86: WeatherCondition("Heavy snow showers", "❄️"),
    95: WeatherCondition("Thunderstorm", "⛈️"),
    96: WeatherCondition("Thunderstorm with light hail", "⛈️"),
    99: WeatherCondition("Thunderstorm with heavy hail", "⛈️"),
}

# A sun emoji at midnight looks wrong, so these codes get a different emoji
# at night. Codes not listed here (rain, snow...) look the same day or night.
NIGHT_EMOJIS: dict[int, str] = {
    0: "🌙",
    1: "🌙",
    2: "☁️",
}

# Returned when Open-Meteo sends a code we don't know (e.g. a new code added
# in the future). Showing "Unknown" is better than crashing the page.
UNKNOWN_CONDITION = WeatherCondition("Unknown conditions", "🌡️")


def get_condition(code: int, is_day: bool = True) -> WeatherCondition:
    """Return the description and emoji for a WMO weather code.

    Args:
        code: The WMO weather code from Open-Meteo (e.g. 61).
        is_day: False at night, so clear-sky codes show a moon instead of a sun.

    Returns:
        The matching WeatherCondition, or UNKNOWN_CONDITION if the code
        isn't recognised.
    """
    condition = WMO_CODES.get(code, UNKNOWN_CONDITION)

    if not is_day and code in NIGHT_EMOJIS:
        # Build a new object instead of changing the shared one (it's frozen).
        return WeatherCondition(condition.description, NIGHT_EMOJIS[code])

    return condition
