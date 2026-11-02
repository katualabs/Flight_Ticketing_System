"""Read-only JSON API v1."""

from __future__ import annotations

from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue

from anga.services import search as search_service

bp = Blueprint("api", __name__, url_prefix="/api/v1")


def ok(data, **meta) -> ResponseReturnValue:
    return jsonify({"ok": True, "data": data, "meta": meta})


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
