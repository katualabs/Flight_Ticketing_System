"""Read-only JSON API v1. Documented in docs/api.md.

Every response uses one envelope: ``{"ok": true, "data": ..., "meta": {...}}`` or
``{"ok": false, "error": {"code": ..., "message": ..., "fields": {...}}}``. No CORS
headers are sent, so browsers on other origins cannot read it.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from anga import clock, validators
from anga.services import search as search_service
from anga.services import status as status_service

bp = Blueprint("api", __name__, url_prefix="/api/v1")


def ok(data, **meta) -> ResponseReturnValue:
    return jsonify({"ok": True, "data": data, "meta": meta})


def fail(status: int, message: str, **details) -> ResponseReturnValue:
    return jsonify({"ok": False, "error": {"code": status, "message": message, **details}}), status


@bp.before_request
def rate_limit() -> ResponseReturnValue | None:
    if current_app.extensions["api_limiter"].allow(request.remote_addr or "unknown"):
        return None
    response, status = fail(429, "Too many requests. Please slow down.")
    response.headers["Retry-After"] = "30"
    return response, status


def _airport_param(name: str, errors: dict[str, str]) -> str | None:
    code = validators.clean(request.args.get(name)).upper()
    if not validators.AIRPORT_RE.match(code):
        errors[name] = "Use a 3-letter airport code."
        return None
    if status_service.airport(code) is None:
        errors[name] = "Unknown airport."
        return None
    return code


def _date_param(name: str, errors: dict[str, str], default: date | None = None) -> date | None:
    text = validators.clean(request.args.get(name))
    if not text and default is not None:
        return default
    parsed = validators.parse_date(text)
    if parsed is None:
        errors[name] = "Use the format YYYY-MM-DD."
    return parsed


def _cabin_param(errors: dict[str, str]) -> str:
    cabin = validators.clean(request.args.get("cabin")) or "Economy"
    if cabin not in validators.CABINS:
        errors["cabin"] = f"Choose one of {', '.join(validators.CABINS)}."
    return cabin


def _invalid(errors: dict[str, str]) -> ResponseReturnValue:
    return fail(400, "Some parameters are invalid.", fields=errors)


@bp.get("/airports")
def airports() -> ResponseReturnValue:
    rows = [
        {
            "code": row["code"],
            "city": row["city"],
            "name": row["name"],
            "country": row["country"],
            "timezone": row["timezone"],
            "lat": row["lat"],
            "lng": row["lng"],
        }
        for row in search_service.airports()
    ]
    return ok(rows, count=len(rows))


def _flight_json(option: search_service.FlightOption) -> dict:
    flight = option.flight
    return {
        "flight_number": flight["flight_number"],
        "date": flight["departure_date"],
        "origin": flight["origin"],
        "destination": flight["destination"],
        "departure_time": flight["departure_time"],
        "arrival_time": flight["arrival_time"],
        "duration_minutes": flight["duration_minutes"],
        "aircraft": flight["aircraft_name"],
        "status": flight["status"],
        "fares": [
            {
                "cabin": fare.cabin,
                "fare_family": fare.family,
                "price": fare.price,
                "currency": "KES",
                "seats_left": fare.seats_left,
                "bags": fare.rules.bags,
                "changeable": fare.rules.can_change,
                "refund_rate": fare.rules.refund_rate,
            }
            for fare in option.fares
        ],
    }


@bp.get("/flights")
def flights() -> ResponseReturnValue:
    errors: dict[str, str] = {}
    origin = _airport_param("from", errors)
    destination = _airport_param("to", errors)
    day = _date_param("date", errors)
    cabin = _cabin_param(errors)
    if day and day < clock.today():
        errors["date"] = "The date cannot be in the past."
    if origin and origin == destination:
        errors["to"] = "Origin and destination must be different."
    if errors:
        return _invalid(errors)
    options = search_service.search_flights(origin, destination, day, cabin, seats_needed=1)
    return ok(
        [_flight_json(option) for option in options],
        count=len(options),
        origin=origin,
        destination=destination,
        date=day.isoformat(),
        cabin=cabin,
    )


@bp.get("/flights/<number>/status")
def flight_status(number: str) -> ResponseReturnValue:
    errors: dict[str, str] = {}
    flight_number = validators.validate_flight_number(number)
    if flight_number is None:
        errors["number"] = "Flight numbers look like AN101."
    day = _date_param("date", errors, default=clock.today())
    if errors:
        return _invalid(errors)
    found = status_service.by_number(flight_number, day)
    if found is None:
        return fail(404, f"{flight_number} does not fly on {day.isoformat()}.")
    return ok(found.as_dict())


@bp.get("/fare-calendar")
def fare_calendar() -> ResponseReturnValue:
    errors: dict[str, str] = {}
    origin = _airport_param("from", errors)
    destination = _airport_param("to", errors)
    cabin = _cabin_param(errors)
    month_text = validators.clean(request.args.get("month"))
    if month_text and not validators.MONTH_RE.match(month_text):
        errors["month"] = "Use the format YYYY-MM."
    if errors:
        return _invalid(errors)
    today = clock.today()
    month = validators.validate_month(month_text, today)
    result = search_service.fare_calendar(origin, destination, month, cabin, today)
    days = [
        {"date": cell.day.isoformat(), "price": cell.price, "currency": "KES", "heat": cell.heat}
        for week in result.weeks
        for cell in week
        if cell is not None and cell.price is not None
    ]
    return ok(
        days,
        month=month.strftime("%Y-%m"),
        origin=origin,
        destination=destination,
        cabin=cabin,
        cheapest=result.cheapest,
        dearest=result.dearest,
    )


@bp.get("/board/<airport>")
def board(airport: str) -> ResponseReturnValue:
    place = status_service.airport(airport.upper())
    if place is None:
        return fail(404, "Unknown airport.")
    kind = request.args.get("type", "departures")
    if kind not in status_service.BOARD_KINDS:
        return fail(400, "Some parameters are invalid.", fields={"type": "departures or arrivals."})
    day = clock.today()
    rows = status_service.board(place["code"], kind, day)
    return ok(
        [row.as_dict() for row in rows],
        count=len(rows),
        airport=place["code"],
        type=kind,
        date=day.isoformat(),
    )
