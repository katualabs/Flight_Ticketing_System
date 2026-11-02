"""Manage a booking: itinerary, seats, extras, changes, cancellation and check-in."""

from __future__ import annotations

from datetime import datetime

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from anga import access, clock, validators
from anga.security import TokenBucketLimiter
from anga.services import booking as booking_service
from anga.services import calendar_ics, checkin, manage, tickets
from anga.services.booking import BookingError

bp = Blueprint("manage", __name__, url_prefix="/manage")

LOOKUP_FAILED = "We could not find a booking with those details."
_lookup_limiter = TokenBucketLimiter(rate_per_minute=20, burst=10)


def _load(reference: str):
    """A booking the visitor may see. Anything else is the same 404, leaking nothing."""
    booking = booking_service.get_by_reference(reference.upper())
    if booking is None or not access.can_view(booking):
        abort(404)
    return booking


@bp.route("/", methods=["GET", "POST"])
def lookup():
    error = None
    values = request.form if request.method == "POST" else request.args
    if request.method == "POST":
        limited = not current_app.testing and not _lookup_limiter.allow(request.remote_addr or "")
        if limited:
            abort(429, description="Too many attempts. Please wait a minute and try again.")
        booking = manage.lookup(request.form.get("reference", ""), request.form.get("email", ""))
        if booking is not None:
            access.grant(booking["reference"])
            return redirect(url_for("manage.itinerary", reference=booking["reference"]))
        error = LOOKUP_FAILED
    return render_template("manage/lookup.html", error=error, values=values), (
        404 if error else 200
    )


@bp.get("/<reference>")
def itinerary(reference: str):
    booking = _load(reference)
    detail = tickets.booking_detail(booking)
    for segment in detail["segments"]:
        segment["checkin"] = checkin.window_for(segment["flight"])
        segment["change"] = manage.can_change(segment["flight"])
        segment["checked_in"] = any(t["record"]["checked_in_at"] for t in segment["tickets"])
    return render_template("manage/itinerary.html", **detail)


def _guarded(reference: str, action, success: str):
    """Run a change, turning rule violations into a message on the itinerary."""
    try:
        action()
        flash(success, "success")
    except BookingError as error:
        flash(str(error), "error")
    return redirect(url_for("manage.itinerary", reference=reference))


@bp.route("/<reference>/seats/<int:segment_id>", methods=["GET", "POST"])
def seats(reference: str, segment_id: int):
    booking = _load(reference)
    if request.method == "POST":
        charged = 0
        try:
            for key, code in request.form.items():
                if not key.startswith("seat_") or not code:
                    continue
                charged += manage.change_seat(
                    booking, segment_id, int(key.removeprefix("seat_")), code.upper()
                )
        except (BookingError, ValueError) as error:
            flash(str(error), "error")
            return redirect(url_for("manage.seats", reference=reference, segment_id=segment_id))
        flash(
            f"Seats updated. KSh {charged:,} charged." if charged else "Seats updated.", "success"
        )
        return redirect(url_for("manage.itinerary", reference=reference))
    try:
        view = manage.seat_change_view(booking, segment_id)
    except BookingError:
        abort(404)
    return render_template("manage/seats.html", booking=booking, **view)


@bp.route("/<reference>/extras", methods=["GET", "POST"])
def extras(reference: str):
    booking = _load(reference)
    if request.method == "POST":
        passenger_id = validators.parse_int(request.form.get("passenger_id"), 0)
        code = validators.clean(request.form.get("code"))
        quantity = validators.parse_int(request.form.get("quantity"), 1)
        return _guarded(
            reference,
            lambda: manage.add_extras(booking, passenger_id, code, quantity),
            "Extra added to your booking.",
        )
    detail = tickets.booking_detail(booking)
    return render_template(
        "manage/extras.html", catalogue=booking_service.extras_catalogue(), **detail
    )


@bp.route("/<reference>/change/<int:segment_id>", methods=["GET", "POST"])
def change(reference: str, segment_id: int):
    booking = _load(reference)
    if request.method == "POST":
        flight_id = validators.parse_int(request.form.get("flight_id"), 0)
        return _guarded(
            reference,
            lambda: manage.change_flight(booking, segment_id, flight_id),
            "Your flight has been changed.",
        )
    day = validators.parse_date(validators.clean(request.args.get("date")))
    detail = tickets.booking_detail(booking)
    segment = next((s for s in detail["segments"] if s["flight"]["segment_id"] == segment_id), None)
    if segment is None:
        abort(404)
    today = clock.today()
    options = None
    if day:
        options = manage.change_options(booking, segment_id, day) if day >= today else []
    return render_template(
        "manage/change.html",
        booking=booking,
        segment=segment,
        allowance=manage.can_change(segment["flight"]),
        options=options,
        selected_date=day,
    )


@bp.route("/<reference>/cancel", methods=["GET", "POST"])
def cancel(reference: str):
    booking = _load(reference)
    if request.method == "POST":
        try:
            refund = manage.cancel(booking)
            flash(f"Booking cancelled. Refund: KSh {refund:,}.", "success")
        except BookingError as error:
            flash(str(error), "error")
        return redirect(url_for("manage.itinerary", reference=reference))
    return render_template(
        "manage/cancel.html",
        quote=manage.cancellation_quote(booking),
        **tickets.booking_detail(booking),
    )


@bp.route("/<reference>/checkin/<int:segment_id>", methods=["GET", "POST"])
def check_in(reference: str, segment_id: int):
    booking = _load(reference)
    if request.method == "POST":
        ids = [
            value
            for value in (validators.parse_int(v) for v in request.form.getlist("passenger"))
            if value is not None
        ]
        try:
            checkin.check_in(booking, segment_id, ids)
        except BookingError as error:
            flash(str(error), "error")
            return redirect(url_for("manage.check_in", reference=reference, segment_id=segment_id))
        flash("You are checked in. Have a good flight!", "success")
        return redirect(url_for("manage.boarding_pass", reference=reference, segment_id=segment_id))
    try:
        view = checkin.segment_view(booking, segment_id)
    except BookingError:
        abort(404)
    return render_template("manage/checkin.html", booking=booking, **view)


@bp.get("/<reference>/boarding/<int:segment_id>")
def boarding_pass(reference: str, segment_id: int):
    booking = _load(reference)
    try:
        view = checkin.boarding_passes(booking, segment_id)
    except BookingError:
        abort(404)
    if not view["passes"]:
        flash("Check in first to get your boarding pass.", "info")
        return redirect(url_for("manage.check_in", reference=reference, segment_id=segment_id))
    return render_template("manage/boarding.html", booking=booking, **view)


@bp.get("/<reference>/calendar.ics")
def calendar(reference: str):
    booking = _load(reference)
    flights = []
    for segment in tickets.booking_detail(booking)["segments"]:
        flight = segment["flight"]
        local = datetime.fromisoformat(f"{flight['departure_date']}T{flight['departure_time']}")
        flights.append(
            calendar_ics.CalendarFlight(
                flight["flight_number"],
                flight["origin"],
                flight["origin_city"],
                flight["destination"],
                flight["destination_city"],
                clock.local_to_utc(local, flight["origin_tz"]),
                flight["duration_minutes"],
            )
        )
    stamped_at = clock.local_to_utc(clock.now(), "Africa/Nairobi")
    body = calendar_ics.build_ics(booking["reference"], flights, stamped_at)
    return Response(
        body,
        mimetype="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{booking["reference"]}.ics"'},
    )
