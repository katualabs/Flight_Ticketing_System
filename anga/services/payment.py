"""Simulated payments. Nothing here contacts a real provider or stores card data."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from sqlite3 import Row

from flask import current_app

from anga import clock
from anga.db import transaction
from anga.repositories import bookings as bookings_repo
from anga.repositories import payments as payments_repo
from anga.services import loyalty, notifications, tickets
from anga.services.booking import flight_departure

CHECKOUT_HOLD_MINUTES = 15
PAY_LATER_HOURS = 24
PAY_LATER_MIN_HOURS_BEFORE_DEPARTURE = 6
MPESA_FAILURE_SUFFIX = "000"


class PaymentError(Exception):
    """The message is safe to show the customer."""


def _new_reference(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(5).upper()}"


def get_payment(reference: str) -> Row | None:
    return payments_repo.get_by_reference(reference)


def checkout_expiry() -> datetime:
    """How long seats stay held while a customer completes payment."""
    return clock.now() + timedelta(minutes=CHECKOUT_HOLD_MINUTES)


def pay_later_expiry(flights: list[Row]) -> datetime:
    """The 24-hour hold, which must also end safely before the first flight."""
    first_departure = min(flight_departure(flight) for flight in flights)
    latest = first_departure - timedelta(hours=PAY_LATER_MIN_HOURS_BEFORE_DEPARTURE)
    deadline = min(clock.now() + timedelta(hours=PAY_LATER_HOURS), latest)
    if deadline <= clock.now():
        raise PaymentError("Pay later is not available this close to departure.")
    return deadline


def confirm_with_payment(booking: Row, payment_id: int | None = None) -> Row:
    """Confirm a booking: status, miles and e-ticket email succeed or fail together."""
    with transaction():
        if payment_id is not None and not payments_repo.settle(payment_id, "succeeded"):
            return bookings_repo.get(booking["id"])
        if not bookings_repo.confirm(booking["id"]):
            raise PaymentError("This booking can no longer be paid.")
        confirmed = bookings_repo.get(booking["id"])
        loyalty.earn_for_booking(confirmed)
        notifications.booking_confirmation(tickets.booking_detail(confirmed))
        return confirmed


def initiate_mpesa(booking: Row, phone: str) -> Row:
    """Record an STK push. It resolves when the status endpoint is next polled."""
    _require_pending(booking)
    now = clock.now()
    settles_at = now + timedelta(seconds=current_app.config["MPESA_SIM_SECONDS"])
    payment_id = payments_repo.insert(
        booking["id"],
        "mpesa",
        booking["total"],
        "initiated",
        _new_reference("MP"),
        now.isoformat(timespec="seconds"),
        phone=phone,
        settles_at=settles_at.isoformat(timespec="seconds"),
    )
    return payments_repo.get_by_id(payment_id)


def poll_mpesa(payment: Row) -> Row:
    """Resolve a push once its simulated delay has passed.

    Safe to call repeatedly: settling is guarded, so a page polled by two tabs
    still confirms and awards miles exactly once.
    """
    if payment["status"] != "initiated":
        return payment
    if clock.now() < datetime.fromisoformat(payment["settles_at"]):
        return payment
    booking = bookings_repo.get(payment["booking_id"])
    if booking["status"] != "Pending" or payment["phone"].endswith(MPESA_FAILURE_SUFFIX):
        payments_repo.settle(payment["id"], "failed")
    else:
        confirm_with_payment(booking, payment["id"])
    return payments_repo.get_by_reference(payment["reference"])


def pay_by_card(booking: Row, last4: str) -> Row:
    """Charge the demo card. Validation has already restricted it to the test number."""
    _require_pending(booking)
    with transaction():
        payment_id = payments_repo.insert(
            booking["id"],
            "card_sim",
            booking["total"],
            "initiated",
            _new_reference("CD"),
            clock.timestamp(),
            card_last4=last4,
        )
        return confirm_with_payment(booking, payment_id)


def record_pay_later(booking: Row) -> Row:
    """Note the promise to pay, then tell the customer about the deadline."""
    with transaction():
        payments_repo.insert(
            booking["id"],
            "pay_later",
            booking["total"],
            "initiated",
            _new_reference("PL"),
            clock.timestamp(),
        )
        notifications.booking_held(tickets.booking_detail(booking))
    return booking


def mark_paid_by_staff(booking: Row) -> Row:
    """An agent records payment taken at a desk."""
    _require_pending(booking)
    with transaction():
        payment_id = payments_repo.insert(
            booking["id"],
            "card_sim",
            booking["total"],
            "initiated",
            _new_reference("DK"),
            clock.timestamp(),
        )
        return confirm_with_payment(booking, payment_id)


def collect_difference(booking: Row, amount: int, reference_prefix: str = "AD") -> None:
    """Record a simulated charge for a post-booking change, on confirmed bookings only."""
    if amount <= 0 or booking["status"] != "Confirmed":
        return
    payments_repo.insert(
        booking["id"],
        "card_sim",
        amount,
        "succeeded",
        _new_reference(reference_prefix),
        clock.timestamp(),
    )


def record_refund(booking: Row, amount: int) -> None:
    if amount <= 0:
        return
    payments_repo.insert(
        booking["id"],
        "card_sim",
        amount,
        "succeeded",
        _new_reference("RF"),
        clock.timestamp(),
        kind="refund",
    )


def _require_pending(booking: Row) -> None:
    if booking["status"] != "Pending":
        raise PaymentError("This booking can no longer be paid.")
