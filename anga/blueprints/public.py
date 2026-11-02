"""Public marketing and information pages."""

from __future__ import annotations

from flask import Blueprint

bp = Blueprint("public", __name__)


@bp.get("/")
def home() -> str:
    return "Anga Air: Fly the East African skies."
