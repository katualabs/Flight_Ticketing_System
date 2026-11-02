"""Simulated email: every message is rendered and written to the outbox table."""

from __future__ import annotations

from sqlite3 import Row

from flask import render_template

from anga import clock
from anga.repositories import outbox as outbox_repo


def send(recipient: str, subject: str, template: str, **context) -> int:
    html_body = render_template(f"emails/{template}.html", subject=subject, **context)
    return outbox_repo.insert(recipient, subject, html_body, clock.timestamp())


def booking_confirmation(detail: dict) -> int:
    booking = detail["booking"]
    return send(
        booking["contact_email"],
        f"Your Anga Air e-ticket: {booking['reference']}",
        "confirmation",
        **detail,
    )


def booking_held(detail: dict) -> int:
    booking = detail["booking"]
    return send(
        booking["contact_email"],
        f"Your seats are held: {booking['reference']}",
        "held",
        **detail,
    )


def booking_cancelled(detail: dict, refund: int) -> int:
    booking = detail["booking"]
    return send(
        booking["contact_email"],
        f"Booking cancelled: {booking['reference']}",
        "cancelled",
        refund=refund,
        **detail,
    )


def booking_changed(detail: dict, message: str) -> int:
    booking = detail["booking"]
    return send(
        booking["contact_email"],
        f"Booking updated: {booking['reference']}",
        "changed",
        message=message,
        **detail,
    )


def flight_cancelled(booking: Row, flight: Row) -> int:
    return send(
        booking["contact_email"],
        f"Flight {flight['flight_number']} cancelled: please rebook",
        "flight_cancelled",
        booking=booking,
        flight=flight,
    )
