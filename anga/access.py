"""Who may see a booking: its owner, staff, or a session that proved reference + email."""

from __future__ import annotations

from sqlite3 import Row

from flask import g, session

VERIFIED_KEY = "verified_bookings"
MAX_VERIFIED = 20


def grant(reference: str) -> None:
    verified = session.get(VERIFIED_KEY, [])
    if reference not in verified:
        session[VERIFIED_KEY] = [*verified, reference][-MAX_VERIFIED:]


def can_view(booking: Row) -> bool:
    user = g.get("user")
    if user is not None:
        if user["role"] in ("agent", "admin"):
            return True
        if booking["user_id"] == user["id"]:
            return True
    return booking["reference"] in session.get(VERIFIED_KEY, [])
