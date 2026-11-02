"""SQL for bookings, their segments and their extras."""

from __future__ import annotations

from collections.abc import Iterable
from sqlite3 import Row

from anga.db import execute, execute_many, fetch_all, fetch_one, fetch_value
from anga.repositories.flights import FLIGHT_SELECT


def reference_exists(reference: str) -> bool:
    return fetch_value("SELECT 1 FROM bookings WHERE reference = ?", (reference,)) is not None


def insert(
    reference: str,
    user_id: int | None,
    contact_email: str,
    contact_phone: str,
    trip_type: str,
    subtotal: int,
    seats_total: int,
    extras_total: int,
    discount: int,
    total: int,
    promo_id: int | None,
    created_at: str,
    expires_at: str | None,
) -> int:
    cursor = execute(
        "INSERT INTO bookings (reference, user_id, contact_email, contact_phone, status,"
        " trip_type, subtotal, seats_total, extras_total, discount, total, promo_id,"
        " created_at, expires_at) VALUES (?, ?, ?, ?, 'Pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            reference,
            user_id,
            contact_email,
            contact_phone,
            trip_type,
            subtotal,
            seats_total,
            extras_total,
            discount,
            total,
            promo_id,
            created_at,
            expires_at,
        ),
    )
    return cursor.lastrowid


def insert_segment(
    booking_id: int, flight_id: int, cabin: str, family: str, direction: str, fare_paid: int
) -> int:
    cursor = execute(
        "INSERT INTO booking_segments (booking_id, flight_id, cabin, fare_family, direction,"
        " fare_paid) VALUES (?, ?, ?, ?, ?, ?)",
        (booking_id, flight_id, cabin, family, direction, fare_paid),
    )
    return cursor.lastrowid


def insert_extras(rows: Iterable[tuple]) -> None:
    execute_many(
        "INSERT INTO booking_extras (booking_id, booking_passenger_id, extra_code, quantity,"
        " line_total) VALUES (?, ?, ?, ?, ?)",
        rows,
    )


def get(booking_id: int) -> Row | None:
    return fetch_one("SELECT * FROM bookings WHERE id = ?", (booking_id,))


def get_by_reference(reference: str) -> Row | None:
    return fetch_one("SELECT * FROM bookings WHERE reference = ?", (reference,))


def segments(booking_id: int) -> list[Row]:
    """Segments joined to their flights, outbound first."""
    return fetch_all(
        "SELECT s.id AS segment_id, s.cabin, s.fare_family, s.direction, s.fare_paid,"
        " s.flight_id, x.* FROM booking_segments s"
        f" JOIN ({FLIGHT_SELECT}) x ON x.id = s.flight_id"
        " WHERE s.booking_id = ? ORDER BY s.direction = 'return'",
        (booking_id,),
    )


def get_segment(segment_id: int) -> Row | None:
    return fetch_one("SELECT * FROM booking_segments WHERE id = ?", (segment_id,))


def update_segment_flight(segment_id: int, flight_id: int, fare_paid: int) -> None:
    execute(
        "UPDATE booking_segments SET flight_id = ?, fare_paid = ? WHERE id = ?",
        (flight_id, fare_paid, segment_id),
    )


def extras(booking_id: int) -> list[Row]:
    return fetch_all(
        "SELECT be.*, e.name, e.type FROM booking_extras be"
        " JOIN extras e ON e.code = be.extra_code WHERE be.booking_id = ? ORDER BY be.id",
        (booking_id,),
    )


def confirm(booking_id: int) -> bool:
    """Move a Pending booking to Confirmed; False if it was no longer Pending."""
    cursor = execute(
        "UPDATE bookings SET status = 'Confirmed', expires_at = NULL"
        " WHERE id = ? AND status = 'Pending'",
        (booking_id,),
    )
    return cursor.rowcount == 1


def cancel(booking_id: int, cancelled_at: str) -> bool:
    """Mark cancelled, never delete: the row is the customer's and auditors' record."""
    cursor = execute(
        "UPDATE bookings SET status = 'Cancelled', cancelled_at = ?, expires_at = NULL"
        " WHERE id = ? AND status <> 'Cancelled'",
        (cancelled_at, booking_id),
    )
    return cursor.rowcount == 1


def expired_holds(now: str) -> list[Row]:
    return fetch_all(
        "SELECT * FROM bookings WHERE status = 'Pending' AND expires_at IS NOT NULL"
        " AND expires_at <= ?",
        (now,),
    )


def add_charges(booking_id: int, seats: int = 0, extras_amount: int = 0, changes: int = 0) -> None:
    execute(
        "UPDATE bookings SET seats_total = seats_total + ?, extras_total = extras_total + ?,"
        " changes_total = changes_total + ?, total = total + ? + ? + ? WHERE id = ?",
        (seats, extras_amount, changes, seats, extras_amount, changes, booking_id),
    )


def set_expiry(booking_id: int, expires_at: str | None) -> None:
    execute("UPDATE bookings SET expires_at = ? WHERE id = ?", (expires_at, booking_id))


def for_user(user_id: int) -> list[Row]:
    return fetch_all(
        "SELECT * FROM bookings WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    )


def attach_user(booking_id: int, user_id: int) -> None:
    execute("UPDATE bookings SET user_id = ? WHERE id = ?", (user_id, booking_id))


def count_for_flight(flight_id: int) -> int:
    return fetch_value("SELECT COUNT(*) FROM booking_segments WHERE flight_id = ?", (flight_id,))


def active_for_flight(flight_id: int) -> list[Row]:
    return fetch_all(
        "SELECT b.* FROM bookings b JOIN booking_segments s ON s.booking_id = b.id"
        " WHERE s.flight_id = ? AND b.status <> 'Cancelled'",
        (flight_id,),
    )


def mark_for_rebooking(booking_id: int) -> None:
    execute("UPDATE bookings SET needs_rebooking = 1 WHERE id = ?", (booking_id,))


def clear_rebooking(booking_id: int) -> None:
    execute("UPDATE bookings SET needs_rebooking = 0 WHERE id = ?", (booking_id,))


def search_admin(
    query: str | None,
    status: str | None,
    flight_number: str | None,
    travel_date: str | None,
    limit: int,
    offset: int | None = 0,
) -> tuple[list[Row], int]:
    """Filtered, paginated booking search for the ops console."""
    clauses, params = [], []
    if query:
        clauses.append("(b.reference LIKE ? OR b.contact_email LIKE ?)")
        params += [f"%{query}%", f"%{query}%"]
    if status:
        clauses.append("b.status = ?")
        params.append(status)
    if flight_number or travel_date:
        flight_clauses = []
        if flight_number:
            flight_clauses.append("f.flight_number = ?")
            params.append(flight_number)
        if travel_date:
            flight_clauses.append("f.departure_date = ?")
            params.append(travel_date)
        clauses.append(
            "b.id IN (SELECT s.booking_id FROM booking_segments s"
            " JOIN flights f ON f.id = s.flight_id"
            f" WHERE {' AND '.join(flight_clauses)})"
        )
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = fetch_value(f"SELECT COUNT(*) FROM bookings b {where}", params)
    rows = fetch_all(
        f"SELECT b.*, (SELECT GROUP_CONCAT(f.flight_number, ', ')"
        " FROM booking_segments s JOIN flights f ON f.id = s.flight_id"
        " WHERE s.booking_id = b.id) AS flights,"
        " (SELECT COUNT(*) FROM booking_passengers p WHERE p.booking_id = b.id) AS passengers"
        f" FROM bookings b {where} ORDER BY b.created_at DESC, b.id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    return rows, total
