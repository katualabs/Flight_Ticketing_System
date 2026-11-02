"""The multi-step booking wizard. State lives server-side in a draft row."""

from __future__ import annotations

import secrets
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from anga import validators
from anga.security import safe_redirect_target
from anga.services import booking as booking_service
from anga.services.booking import BookingError

bp = Blueprint("booking", __name__, url_prefix="/book")

DRAFT_SESSION_KEY = "draft_token"
STEPS = ("passengers", "seats", "extras", "review", "pay")


def draft_required(view):
    """Load the visitor's draft into ``g.draft`` or send them back to search."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        g.draft = booking_service.load_draft(session.get(DRAFT_SESSION_KEY))
        if g.draft is None:
            flash("Your booking session has ended. Please search again.", "info")
            return redirect(url_for("public.home"))
        return view(*args, **kwargs)

    return wrapped


def _save_draft() -> None:
    booking_service.save_draft(session[DRAFT_SESSION_KEY], g.draft)


def _render(template: str, step: str, **context):
    return render_template(
        template,
        step=step,
        steps=STEPS,
        draft=g.draft,
        flights=booking_service.draft_flights(g.draft),
        quote=context.pop("quote", None) or booking_service.quote_draft(g.draft),
        **context,
    )


@bp.post("/start")
def start():
    """Create a draft from the fares chosen on the results page."""
    back = safe_redirect_target(request.form.get("back"), url_for("public.home"))
    party, errors = validators.validate_party(request.form)
    outbound = validators.parse_int(request.form.get("outbound_fare"))
    inbound = validators.parse_int(request.form.get("return_fare"))
    if errors:
        flash(next(iter(errors.values())), "error")
        return redirect(back)
    if request.form.get("trip") == "round_trip" and not inbound:
        flash("Please choose a return flight.", "error")
        return redirect(back)
    try:
        draft = booking_service.new_draft(
            outbound, inbound, party["adults"], party["children"], party["infants"]
        )
    except BookingError as error:
        flash(str(error), "error")
        return redirect(back)
    token = secrets.token_urlsafe(24)
    session[DRAFT_SESSION_KEY] = token
    booking_service.save_draft(token, draft)
    booking_service.purge_old_drafts()
    return redirect(url_for("booking.passengers"))


@bp.route("/passengers", methods=["GET", "POST"])
@draft_required
def passengers():
    errors: dict[str, str] = {}
    values = request.form if request.method == "POST" else None
    if request.method == "POST":
        first_flight = booking_service.draft_flights(g.draft)[0]
        people, contact, errors = validators.validate_passengers(
            request.form,
            g.draft["passenger_types"],
            validators.parse_date(first_flight["departure_date"]),
        )
        if not errors:
            g.draft["passengers"] = people
            g.draft["contact"] = contact
            _save_draft()
            return redirect(url_for("booking.seats"))
    return _render(
        "booking/passengers.html",
        "passengers",
        errors=errors,
        values=values,
        saved_travellers=[],
    ), (400 if errors else 200)


def _require_passengers():
    if not g.draft["passengers"]:
        return redirect(url_for("booking.passengers"))
    return None


@bp.route("/seats", methods=["GET", "POST"])
@draft_required
def seats():
    guard = _require_passengers()
    if guard:
        return guard
    errors: dict[str, str] = {}
    if request.method == "POST":
        chosen = validators.parse_seat_choices(request.form, g.draft)
        errors = booking_service.validate_seat_choices(g.draft, chosen)
        if not errors:
            g.draft["seats"] = chosen
            _save_draft()
            return redirect(url_for("booking.extras"))
        flash(next(iter(errors.values())), "error")
    maps = [
        booking_service.seat_map(segment["flight_id"], flight["aircraft_code"], segment["cabin"])
        for segment, flight in zip(
            g.draft["segments"], booking_service.draft_flights(g.draft), strict=True
        )
    ]
    return _render(
        "booking/seats.html",
        "seats",
        maps=maps,
        errors=errors,
        seated=booking_service.non_infant_indexes(g.draft),
    ), (409 if errors else 200)


@bp.route("/extras", methods=["GET", "POST"])
@draft_required
def extras():
    guard = _require_passengers()
    if guard:
        return guard
    catalogue = booking_service.extras_catalogue()
    if request.method == "POST":
        g.draft["extras"] = validators.parse_extras(request.form, g.draft, catalogue)
        _save_draft()
        return redirect(url_for("booking.review"))
    return _render(
        "booking/extras.html",
        "extras",
        catalogue=catalogue,
        seated=booking_service.non_infant_indexes(g.draft),
    )


@bp.route("/review", methods=["GET", "POST"])
@draft_required
def review():
    guard = _require_passengers()
    if guard:
        return guard
    if request.method == "POST":
        if request.form.get("action") == "remove_promo":
            g.draft["promo"] = None
            _save_draft()
        else:
            quote = booking_service.apply_promo_code(g.draft, request.form.get("promo", ""))
            _save_draft()
            flash(
                quote.promo_message or "Enter a promo code first.",
                "success" if quote.promo_ok else "error",
            )
        return redirect(url_for("booking.review"))
    return _render(
        "booking/review.html",
        "review",
        rules=booking_service.fare_rules_for(g.draft),
    )


@bp.post("/quote")
@draft_required
def quote():
    """Re-price the current form without saving it, for the live summary."""
    if not g.draft["passengers"]:
        abort(409)
    preview = dict(g.draft)
    if request.form.get("step") == "seats":
        preview["seats"] = validators.parse_seat_choices(request.form, g.draft)
    elif request.form.get("step") == "extras":
        preview["extras"] = validators.parse_extras(
            request.form, g.draft, booking_service.extras_catalogue()
        )
    return render_template("booking/_summary.html", quote=booking_service.quote_draft(preview))
