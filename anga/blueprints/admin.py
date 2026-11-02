"""The operations console. Admins have full access; agents run bookings and flight status."""

from __future__ import annotations

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from anga import clock, validators
from anga.security import admin_required, staff_required
from anga.services import analytics, ops
from anga.services.ops import OpsError

bp = Blueprint("admin", __name__, url_prefix="/admin")

# (endpoint, label, admin only). Agents can run bookings and flight status, but
# prices, promos, users and settings are for admins alone.
NAVIGATION = (
    ("admin.dashboard", "Dashboard", False),
    ("admin.flights", "Flights", False),
    ("admin.bookings", "Bookings", False),
    ("admin.promos", "Promo codes", True),
    ("admin.users", "Users", True),
    ("admin.messages", "Messages", False),
    ("admin.outbox", "Outbox", False),
    ("admin.audit_log", "Audit log", True),
    ("admin.settings", "Settings", True),
)
ROLES = ("customer", "agent", "admin")


@bp.context_processor
def inject_navigation() -> dict:
    is_admin = g.user is not None and g.user["role"] == "admin"
    return {
        "admin_nav": [
            (endpoint, label)
            for endpoint, label, admin_only in NAVIGATION
            if endpoint in current_app.view_functions and (is_admin or not admin_only)
        ],
        "is_admin": is_admin,
        "admin_endpoints": set(current_app.view_functions),
    }


def _page() -> int:
    return max(validators.parse_int(request.args.get("page"), 1) or 1, 1)


def _active(filters: dict) -> dict:
    """Only the filters in use, for building links that keep them."""
    return {key: value for key, value in filters.items() if value}


def _csv_response(body: str, filename: str) -> Response:
    return Response(
        body,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.get("/")
@staff_required
def dashboard():
    return render_template("admin/dashboard.html", **analytics.dashboard())


# ---------------------------------------------------------------------- flights


def _flight_or_404(flight_id: int):
    flight = ops.get_flight(flight_id)
    if flight is None:
        abort(404)
    return flight


@bp.get("/flights")
@staff_required
def flights():
    args = request.args
    query = validators.clean(args.get("q")) or None
    origin = validators.clean(args.get("origin")) or None
    day = validators.clean(args.get("date")) or None
    status = validators.clean(args.get("status")) or None
    page = _page()
    rows, total = ops.search_flights(query, origin, day, status, page)
    return render_template(
        "admin/flights.html",
        rows=rows,
        total=total,
        page=page,
        pages=ops.pages_for(total),
        airports=ops.airports(),
        statuses=validators.FLIGHT_STATUSES,
        filters={"q": query, "origin": origin, "date": day, "status": status},
        active=_active({"q": query, "origin": origin, "date": day, "status": status}),
    )


@bp.route("/flights/new", methods=["GET", "POST"])
@admin_required
def new_flight():
    errors: dict[str, str] = {}
    if request.method == "POST":
        data, errors = validators.validate_flight(request.form, clock.today())
        if not errors:
            try:
                flight_id = ops.create_flight(g.user["id"], data)
            except OpsError as error:
                errors["flight_number"] = str(error)
            else:
                flash("Flight created.", "success")
                return redirect(url_for("admin.flight_detail", flight_id=flight_id))
    return render_template(
        "admin/flight_form.html",
        errors=errors,
        values=request.form,
        airport_options=[(a["code"], f"{a['city']} ({a['code']})") for a in ops.airports()],
        aircraft_options=[(a["code"], a["name"]) for a in ops.aircraft()],
    ), (400 if errors else 200)


@bp.get("/flights/<int:flight_id>")
@staff_required
def flight_detail(flight_id: int):
    return render_template(
        "admin/flight_detail.html",
        flight=_flight_or_404(flight_id),
        fares=ops.fares_for(flight_id),
        statuses=validators.FLIGHT_STATUSES,
    )


@bp.post("/flights/<int:flight_id>/times")
@admin_required
def update_flight_times(flight_id: int):
    flight = _flight_or_404(flight_id)
    departure = validators.clean(request.form.get("departure_time"))
    duration = validators.parse_int(request.form.get("duration_minutes"), 0)
    if not validators.TIME_RE.match(departure) or not 0 < duration <= 1440:
        flash("Enter a valid departure time and duration.", "error")
    else:
        ops.update_flight_times(g.user["id"], flight, departure, duration)
        flash("Flight times updated.", "success")
    return redirect(url_for("admin.flight_detail", flight_id=flight_id))


@bp.post("/flights/<int:flight_id>/fares/<int:fare_id>")
@admin_required
def update_fare(flight_id: int, fare_id: int):
    fare = ops.get_fare(fare_id)
    if fare is None or fare["flight_id"] != flight_id:
        abort(404)
    data, errors = validators.validate_fare(request.form)
    if errors:
        flash(next(iter(errors.values())), "error")
    else:
        try:
            ops.update_fare(
                g.user["id"], fare, data["price"], data["total_seats"], data["available_seats"]
            )
            flash(f"{fare['cabin']} {fare['fare_family']} updated.", "success")
        except OpsError as error:
            flash(str(error), "error")
    return redirect(url_for("admin.flight_detail", flight_id=flight_id))


@bp.post("/flights/<int:flight_id>/delete")
@admin_required
def delete_flight(flight_id: int):
    flight = _flight_or_404(flight_id)
    try:
        ops.delete_flight(g.user["id"], flight)
    except OpsError as error:
        flash(str(error), "error")
        return redirect(url_for("admin.flight_detail", flight_id=flight_id))
    flash("Flight deleted.", "success")
    return redirect(url_for("admin.flights"))


@bp.post("/flights/<int:flight_id>/cancel")
@admin_required
def cancel_flight(flight_id: int):
    flight = _flight_or_404(flight_id)
    try:
        affected = ops.cancel_flight(g.user["id"], flight)
        flash(f"Flight cancelled. {affected} booking(s) marked for rebooking.", "success")
    except OpsError as error:
        flash(str(error), "error")
    return redirect(url_for("admin.flight_detail", flight_id=flight_id))


@bp.route("/flights/generate", methods=["GET", "POST"])
@admin_required
def generate_schedule():
    errors: dict[str, str] = {}
    if request.method == "POST":
        data, errors = validators.validate_bulk_schedule(request.form, clock.today())
        if not errors:
            try:
                created, skipped = ops.bulk_generate(
                    g.user["id"],
                    data["flight_number"],
                    data["start"],
                    data["end"],
                    data["weekdays"],
                )
            except OpsError as error:
                errors["flight_number"] = str(error)
            else:
                flash(f"{created} flight(s) created, {skipped} already existed.", "success")
                return redirect(url_for("admin.flights"))
    return render_template(
        "admin/generate.html",
        errors=errors,
        values=request.form,
        routes=ops.route_templates(),
    ), (400 if errors else 200)
