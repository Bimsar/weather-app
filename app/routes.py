"""Flask routes (URL handlers).

Routes only deal with the web side: reading the request, calling the
weather service, and choosing which template to show. They contain no API
or JSON logic; that all lives in weather_service.py.
"""

from flask import Blueprint, render_template, request

from app.weather_service import (
    CityNotFoundError,
    WeatherAPIError,
    get_weather,
    search_cities,
)

# A Blueprint is a group of related routes. The app registers it in create_app().
main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index() -> str:
    """Show the home page with an empty search form."""
    return render_template("index.html")


@main_bp.route("/search")
def search() -> tuple[str, int] | str:
    """Search for a city and show its current weather.

    The form uses GET, so the city appears in the URL (?city=London).
    That means users can bookmark or share a search.

    Each kind of failure gets its own message AND its own HTTP status code,
    so both people and tests can tell what went wrong.
    """
    # .strip() removes spaces, so "   " counts as an empty search.
    city = request.args.get("city", "").strip()

    if not city:
        # 400 = "Bad Request": the user sent something we can't use.
        return render_template("index.html", error="Please enter a city name."), 400

    try:
        # Stage 7 will let the user pick when several cities match;
        # for now we use the best match, which the API lists first.
        location = search_cities(city)[0]
        report = get_weather(location)
    except CityNotFoundError:
        # 404 = "Not Found". Stay on the search page so the user can retry.
        message = f"We couldn't find a city called “{city}”. Check the spelling and try again."
        return render_template("index.html", city=city, error=message), 404
    except WeatherAPIError as error:
        # 503 = "Service Unavailable": the problem is on the API's side,
        # not the user's, so show the dedicated error page.
        return render_template("error.html", message=str(error)), 503

    return render_template("index.html", city=city, report=report)


# app_errorhandler (instead of errorhandler) applies to the WHOLE app,
# not just this blueprint, so every unknown URL gets the friendly page.
@main_bp.app_errorhandler(404)
def page_not_found(error: Exception) -> tuple[str, int]:
    """Friendly page for URLs that don't exist."""
    return render_template("error.html", message="That page doesn't exist."), 404


@main_bp.app_errorhandler(500)
def internal_error(error: Exception) -> tuple[str, int]:
    """Friendly page for unexpected crashes (instead of a raw stack trace)."""
    return render_template(
        "error.html", message="Something went wrong on our side. Please try again."
    ), 500
