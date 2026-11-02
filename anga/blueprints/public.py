"""Public marketing and information pages, flight status and display preferences."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from anga import clock, validators
from anga.i18n import LANGUAGES
from anga.security import safe_redirect_target
from anga.services import contact as contact_service
from anga.services import search as search_service
from anga.services import status as status_service

bp = Blueprint("public", __name__)


@bp.get("/")
def home() -> str:
    today = clock.today()
    return render_template(
        "public/home.html",
        airports=search_service.airports(),
        destinations=search_service.destination_fares(today),
        deals=search_service.lowest_fares(today),
        network=search_service.route_map(today),
    )


@bp.get("/destinations")
def destinations() -> str:
    return render_template(
        "public/destinations.html", destinations=search_service.destination_fares(clock.today())
    )


@bp.get("/about")
def about() -> str:
    return render_template("public/about.html")


@bp.get("/faq")
def faq() -> str:
    return render_template("public/faq.html")


@bp.get("/terms")
def terms() -> str:
    return render_template("public/terms.html")


@bp.get("/privacy")
def privacy() -> str:
    return render_template("public/privacy.html")


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    errors: dict[str, str] = {}
    values = request.form
    if request.method == "POST":
        data, errors = validators.validate_contact(request.form)
        if not errors:
            contact_service.submit(data)
            flash("Thanks! Your message has been received.", "success")
            return redirect(url_for("public.contact"))
    return render_template("public/contact.html", errors=errors, values=values), (
        400 if errors else 200
    )


@bp.get("/status")
def status() -> str:
    today = clock.today()
    args = request.args
    day = validators.parse_date(validators.clean(args.get("date"))) or today
    number = validators.clean(args.get("number")).upper()
    origin = validators.clean(args.get("from")).upper() or "NBO"
    destination = validators.clean(args.get("to")).upper() or "MBA"
    mode = args.get("mode")
    results = []
    if mode == "number":
        flight_number = validators.validate_flight_number(number)
        found = status_service.by_number(flight_number, day) if flight_number else None
        results = [found] if found else []
    elif mode == "route":
        results = status_service.by_route(origin, destination, day)
    return render_template(
        "public/status.html",
        airports=search_service.airports(),
        results=results,
        searched=mode in ("number", "route"),
        query={
            "number": number,
            "date": day.isoformat(),
            "origin": origin,
            "destination": destination,
        },
    )


@bp.get("/status/board/<airport>")
def board(airport: str) -> str:
    place = status_service.airport(airport.upper())
    if place is None:
        abort(404)
    kind = request.args.get("type", "departures")
    kind = kind if kind in status_service.BOARD_KINDS else "departures"
    day = clock.today()
    return render_template(
        "public/board.html",
        airport=place,
        kind=kind,
        day=day,
        rows=status_service.board(place["code"], kind, day),
    )


def _back() -> str:
    return safe_redirect_target(request.form.get("next"), url_for("public.home"))


@bp.post("/preferences/language")
def set_language():
    language = request.form.get("lang")
    if language in LANGUAGES:
        session["lang"] = language
    return redirect(_back())


@bp.post("/preferences/currency")
def set_currency():
    """Display only: bookings are always charged in shillings."""
    currency = request.form.get("currency")
    if currency in ("KES", "USD"):
        session["currency"] = currency
    return redirect(_back())
