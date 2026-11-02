"""SQL for payment attempts and refunds. Rows are append-only history."""

from __future__ import annotations

from sqlite3 import Row

from anga.db import execute, fetch_all, fetch_one, fetch_value


def insert(
    booking_id: int,
    method: str,
    amount: int,
    status: str,
    reference: str,
    created_at: str,
    kind: str = "charge",
    phone: str | None = None,
    card_last4: str | None = None,
    settles_at: str | None = None,
) -> int:
    cursor = execute(
        "INSERT INTO payments (booking_id, method, kind, amount, status, reference, phone,"
        " card_last4, created_at, settles_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (booking_id, method, kind, amount, status, reference, phone, card_last4, created_at,
         settles_at),
    )  # fmt: skip
    return cursor.lastrowid


def get_by_id(payment_id: int) -> Row | None:
    return fetch_one("SELECT * FROM payments WHERE id = ?", (payment_id,))


def get_by_reference(reference: str) -> Row | None:
    return fetch_one("SELECT * FROM payments WHERE reference = ?", (reference,))


def for_booking(booking_id: int) -> list[Row]:
    return fetch_all(
        "SELECT * FROM payments WHERE booking_id = ? ORDER BY created_at, id", (booking_id,)
    )


def settle(payment_id: int, status: str) -> bool:
    """Resolve an initiated payment exactly once, so polling cannot double-settle."""
    cursor = execute(
        "UPDATE payments SET status = ? WHERE id = ? AND status = 'initiated'",
        (status, payment_id),
    )
    return cursor.rowcount == 1


def amount_paid(booking_id: int) -> int:
    """Net money held for a booking: successful charges minus refunds."""
    value = fetch_value(
        "SELECT COALESCE(SUM(CASE kind WHEN 'charge' THEN amount ELSE -amount END), 0)"
        " FROM payments WHERE booking_id = ? AND status = 'succeeded'",
        (booking_id,),
    )
    return int(value)
