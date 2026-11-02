"""HTML error pages, with JSON for API routes."""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from anga.i18n import t


def _page(code: int) -> tuple[str, str]:
    pages = {
        400: (t("error.bad_request_title"), ""),
        403: (t("error.forbidden_title"), t("error.forbidden_body")),
        404: (t("error.not_found_title"), t("error.not_found_body")),
        413: (t("error.too_large_title"), ""),
        429: (t("error.too_many_title"), ""),
    }
    return pages.get(code, (t("error.server_title"), t("error.server_body")))


def init_app(app: Flask) -> None:
    @app.errorhandler(HTTPException)
    def handle_http(error: HTTPException):
        if request.path.startswith("/api/"):
            return jsonify(
                {"ok": False, "error": {"code": error.code, "message": error.description}}
            ), error.code
        title, body = _page(error.code)
        if error.code in (400, 429):
            body = error.description
        return render_template("error.html", title=title, body=body), error.code

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        app.logger.exception("Unhandled error", exc_info=error)
        if request.path.startswith("/api/"):
            return jsonify(
                {"ok": False, "error": {"code": 500, "message": "Internal server error."}}
            ), 500
        title, body = _page(500)
        return render_template("error.html", title=title, body=body), 500
