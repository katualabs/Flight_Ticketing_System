"""Read-only JSON API v1."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from anga import clock
from anga.services import search as search_service
from anga.services import status as status_service

bp = Blueprint("api", __name__, url_prefix="/api/v1")


def ok(data, **meta) -> ResponseReturnValue:
    return jsonify({"ok": True, "data": data, "meta": meta})


def fail(status: int, message: str, **details) -> ResponseReturnValue:
    return jsonify({"ok": False, "error": {"code": status, "message": message, **details}}), status


@bp.get("/airports")
def airports() -> ResponseReturnValue:
    return ok(
        [
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
    )


@bp.get("/board/<airport>")
def board(airport: str) -> ResponseReturnValue:
    place = status_service.airport(airport.upper())
    if place is None:
        return fail(404, "Unknown airport.")
    kind = request.args.get("type", "departures")
    if kind not in status_service.BOARD_KINDS:
        return fail(400, "type must be departures or arrivals.")
    day = clock.today()
    rows = status_service.board(place["code"], kind, day)
    return ok(
        [row.as_dict() for row in rows], airport=place["code"], type=kind, date=day.isoformat()
    )
