"""Public marketing and information pages."""

from __future__ import annotations

from flask import Blueprint, render_template

from anga import clock
from anga.services import search as search_service

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
