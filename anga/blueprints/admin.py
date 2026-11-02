"""The operations console. Admins have full access; agents run bookings and flight status."""

from __future__ import annotations

from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    render_template,
    request,
)

from anga import validators
from anga.security import staff_required
from anga.services import analytics

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
