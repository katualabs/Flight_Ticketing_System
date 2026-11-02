"""The multi-step booking wizard. State lives server-side in a draft row."""

from __future__ import annotations

import secrets
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from anga import access, clock, validators
from anga.security import safe_redirect_target
from anga.services import booking as booking_service
from anga.services import payment as payment_service
from anga.services import tickets
from anga.services.booking import BookingError, PriceChangedError
from anga.services.payment import PaymentError

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


@bp.route("/pay", methods=["GET", "POST"])
@draft_required
def pay():
    """Choosing how to pay is what actually creates the booking."""
    guard = _require_passengers()
    if guard:
        return guard
    errors: dict[str, str] = {}
    if request.method == "POST":
        method = request.form.get("method")
        details, errors = _validate_method(method)
        if not errors:
            try:
                return _create_and_charge(method, details)
            except PriceChangedError as error:
                flash(str(error), "warning")
                return redirect(url_for("booking.review"))
            except (BookingError, PaymentError) as error:
                flash(str(error), "error")
                return redirect(url_for("booking.seats"))
    return _render(
        "booking/pay.html", "pay", errors=errors, active=request.form.get("method", "mpesa")
    ), (400 if errors else 200)


def _validate_method(method: str | None) -> tuple[dict, dict[str, str]]:
    if method == "mpesa":
        phone, problem = validators.validate_mpesa_phone(request.form.get("mpesa_phone", ""))
        return {"phone": phone}, ({"mpesa_phone": problem} if problem else {})
    if method == "card_sim":
        return validators.validate_demo_card(request.form, clock.today())
    if method == "pay_later":
        return {}, {}
    return {}, {"method": "Choose a payment method."}


def _create_and_charge(method: str, details: dict):
    flights = booking_service.draft_flights(g.draft)
    expires_at = (
        payment_service.pay_later_expiry(flights)
        if method == "pay_later"
        else payment_service.checkout_expiry()
    )
    expected = validators.parse_int(request.form.get("expected_total"))
    created = booking_service.create_booking(
        g.draft,
        user_id=g.user["id"] if g.get("user") else None,
        expires_at=expires_at,
        expected_total=expected,
    )
    access.grant(created["reference"])
    booking_service.delete_draft(session.pop(DRAFT_SESSION_KEY))
    return _charge(created, method, details)


def _charge(booking, method: str, details: dict):
    if method == "mpesa":
        payment = payment_service.initiate_mpesa(booking, details["phone"])
        return redirect(url_for("booking.mpesa_wait", payment_ref=payment["reference"]))
    if method == "card_sim":
        payment_service.pay_by_card(booking, details["last4"])
        flash("Payment received. Your trip is confirmed.", "success")
    else:
        payment_service.record_pay_later(booking)
        flash("Your seats are held for 24 hours.", "info")
    return redirect(url_for("booking.confirmation", reference=booking["reference"]))


def _viewable_booking(reference: str):
    booking = booking_service.get_by_reference(reference)
    if booking is None or not access.can_view(booking):
        abort(404)
    return booking


@bp.route("/pay/<reference>", methods=["GET", "POST"])
def pay_existing(reference: str):
    """Pay for, or retry paying for, a booking that is already held."""
    booking = _viewable_booking(reference)
    if booking["status"] != "Pending":
        return redirect(url_for("booking.confirmation", reference=reference))
    errors: dict[str, str] = {}
    if request.method == "POST":
        method = request.form.get("method")
        details, errors = _validate_method(method)
        if method == "pay_later":
            errors = {"method": "This booking is already on hold."}
        if not errors:
            try:
                return _charge(booking, method, details)
            except PaymentError as error:
                flash(str(error), "error")
                return redirect(url_for("booking.confirmation", reference=reference))
    return render_template(
        "booking/pay_existing.html",
        booking=booking,
        errors=errors,
        active=request.form.get("method", "mpesa"),
    ), (400 if errors else 200)


def _viewable_payment(payment_ref: str):
    payment = payment_service.get_payment(payment_ref)
    if payment is None:
        abort(404)
    booking = booking_service.get_booking(payment["booking_id"])
    if not access.can_view(booking):
        abort(404)
    return payment, booking


@bp.get("/mpesa/<payment_ref>")
def mpesa_wait(payment_ref: str):
    """The "check your phone" screen. It also works without JS by refreshing itself."""
    payment, booking = _viewable_payment(payment_ref)
    payment = payment_service.poll_mpesa(payment)
    if payment["status"] == "succeeded":
        flash("M-Pesa payment received. Your trip is confirmed.", "success")
        return redirect(url_for("booking.confirmation", reference=booking["reference"]))
    return render_template("booking/mpesa.html", payment=payment, booking=booking)


@bp.get("/payment-status/<payment_ref>")
def payment_status(payment_ref: str):
    payment, booking = _viewable_payment(payment_ref)
    payment = payment_service.poll_mpesa(payment)
    return jsonify(
        {
            "status": payment["status"],
            "redirect": url_for("booking.mpesa_wait", payment_ref=payment_ref),
        }
    )


@bp.get("/confirmation/<reference>")
def confirmation(reference: str):
    booking = _viewable_booking(reference)
    return render_template("booking/confirmation.html", **tickets.booking_detail(booking))
