"""Tests for app/weather_codes.py.

These are unit tests: they test one small function in isolation.
No Flask app and no internet are needed.
"""

import pytest

from app.weather_codes import (
    NIGHT_EMOJIS,
    UNKNOWN_CONDITION,
    WMO_CODES,
    WeatherCondition,
    get_condition,
)


# --- Positive tests: valid input gives the expected output ----------------

# parametrize runs the same test once per row, so one test function checks
# many codes. Each row shows up as a separate test in the results.
@pytest.mark.parametrize(
    ("code", "description", "emoji"),
    [
        (0, "Clear sky", "☀️"),
        (3, "Overcast", "☁️"),
        (45, "Fog", "🌫️"),
        (61, "Light rain", "🌧️"),
        (75, "Heavy snow", "❄️"),
        (95, "Thunderstorm", "⛈️"),
    ],
)
def test_known_codes_return_correct_condition(
    code: int, description: str, emoji: str
) -> None:
    """Known codes map to the right description and emoji (daytime)."""
    condition = get_condition(code)

    assert condition.description == description
    assert condition.emoji == emoji


def test_get_condition_returns_weather_condition_object() -> None:
    """The function returns a dataclass, not a raw dict or tuple."""
    assert isinstance(get_condition(0), WeatherCondition)


# --- Day vs night ----------------------------------------------------------

@pytest.mark.parametrize(
    ("code", "night_emoji"),
    [(0, "🌙"), (1, "🌙"), (2, "☁️")],
)
def test_clear_codes_show_night_emoji_at_night(code: int, night_emoji: str) -> None:
    """Clear/partly cloudy skies show a moon or cloud at night, not a sun."""
    condition = get_condition(code, is_day=False)

    assert condition.emoji == night_emoji
    # The text must not change, only the emoji.
    assert condition.description == WMO_CODES[code].description


def test_rain_looks_the_same_day_and_night() -> None:
    """Codes without a night emoji are unchanged at night."""
    assert get_condition(61, is_day=False) == get_condition(61, is_day=True)


def test_night_lookup_does_not_change_shared_daytime_data() -> None:
    """Asking for night must not overwrite the daytime emoji for later calls.

    This guards against a classic bug: modifying a shared object.
    """
    get_condition(0, is_day=False)

    assert get_condition(0).emoji == "☀️"


# --- Negative tests: invalid input is handled safely ----------------------

# NEGATIVE TEST: we give the function input it should NOT recognise and check
# it fails gracefully (a sensible default) instead of crashing.
@pytest.mark.parametrize("code", [4, 50, 1000])
def test_unknown_code_returns_default(code: int) -> None:
    """Codes that aren't in the WMO table return the 'unknown' condition."""
    assert get_condition(code) == UNKNOWN_CONDITION


def test_unknown_code_at_night_returns_default() -> None:
    """Unknown codes still return the default at night (no crash)."""
    assert get_condition(1000, is_day=False) == UNKNOWN_CONDITION


# --- Boundary tests: values at the edges of the valid range ---------------

# BOUNDARY VALUE ANALYSIS: bugs often hide at the edges of a range.
# Valid WMO codes go from 0 (lowest) to 99 (highest), so we test exactly on
# each edge AND just outside each edge.
@pytest.mark.parametrize(
    ("code", "expected_description"),
    [
        (-1, UNKNOWN_CONDITION.description),   # just below the lowest valid code
        (0, "Clear sky"),                      # lowest valid code
        (99, "Thunderstorm with heavy hail"),  # highest valid code
        (100, UNKNOWN_CONDITION.description),  # just above the highest valid code
    ],
)
def test_code_range_boundaries(code: int, expected_description: str) -> None:
    """Codes on and just outside the 0–99 range are handled correctly."""
    assert get_condition(code).description == expected_description


# --- Data integrity --------------------------------------------------------

def test_every_code_has_description_and_emoji() -> None:
    """No entry in the table is missing text or an emoji."""
    for code, condition in WMO_CODES.items():
        assert condition.description, f"code {code} has no description"
        assert condition.emoji, f"code {code} has no emoji"


def test_every_night_emoji_belongs_to_a_known_code() -> None:
    """A night emoji for a code that doesn't exist would be a typo."""
    assert set(NIGHT_EMOJIS) <= set(WMO_CODES)
