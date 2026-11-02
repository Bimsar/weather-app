"""Flask routes (URL handlers).

Routes only deal with the web side: reading the request and choosing which
template to show. All weather/API logic will live in weather_service.py.
"""

from flask import Blueprint, render_template, request

# A Blueprint is a group of related routes. The app registers it in create_app().
main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index() -> str:
    """Show the home page with an empty search form."""
    return render_template("index.html")


@main_bp.route("/search")
def search() -> tuple[str, int] | str:
    """Handle the search form.

    The form uses GET, so the city appears in the URL (?city=London).
    That means users can bookmark or share a search.
    """
    # .strip() removes spaces, so "   " counts as an empty search.
    city = request.args.get("city", "").strip()

    if not city:
        # 400 = "Bad Request": the user sent something we can't use.
        return render_template("index.html", error="Please enter a city name."), 400

    # Temporary: real weather results arrive in Stage 6.
    return render_template("index.html", city=city)
