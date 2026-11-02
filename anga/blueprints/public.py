"""Public marketing and information pages."""

from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("public", __name__)


@bp.get("/")
def home() -> str:
    return render_template("public/home.html")


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
