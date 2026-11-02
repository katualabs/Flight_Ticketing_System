"""SQL for passengers and their per-segment seat and check-in records."""

from __future__ import annotations

from sqlite3 import Row

from anga.db import execute, fetch_all, fetch_one, fetch_value


def insert(
    booking_id: int,
    full_name: str,
    id_number: str,
    date_of_birth: str | None,
    passenger_type: str,
) -> int:
    cursor = execute(
        "INSERT INTO booking_passengers (booking_id, full_name, id_number, date_of_birth,"
        " passenger_type) VALUES (?, ?, ?, ?, ?)",
        (booking_id, full_name, id_number, date_of_birth, passenger_type),
    )
    return cursor.lastrowid


def for_booking(booking_id: int) -> list[Row]:
    return fetch_all(
        "SELECT * FROM booking_passengers WHERE booking_id = ? ORDER BY id", (booking_id,)
    )


def insert_seat_record(
    passenger_id: int, segment_id: int, seat_id: int | None, seat_price_paid: int
) -> None:
    execute(
        "INSERT INTO passenger_seats (booking_passenger_id, segment_id, seat_id,"
        " seat_price_paid) VALUES (?, ?, ?, ?)",
        (passenger_id, segment_id, seat_id, seat_price_paid),
    )


SEAT_RECORD_SELECT = """
    SELECT ps.*, p.full_name, p.id_number, p.passenger_type, p.booking_id,
           s.seat_code, s.cabin AS seat_cabin, s.is_window, s.is_aisle, s.extra_legroom,
           s.price_extra
    FROM passenger_seats ps
    JOIN booking_passengers p ON p.id = ps.booking_passenger_id
    LEFT JOIN seats s ON s.id = ps.seat_id
"""


def seat_records_for_segment(segment_id: int) -> list[Row]:
    return fetch_all(f"{SEAT_RECORD_SELECT} WHERE ps.segment_id = ? ORDER BY p.id", (segment_id,))


def seat_record(passenger_id: int, segment_id: int) -> Row | None:
    return fetch_one(
        f"{SEAT_RECORD_SELECT} WHERE ps.booking_passenger_id = ? AND ps.segment_id = ?",
        (passenger_id, segment_id),
    )


def update_seat_record(
    passenger_id: int, segment_id: int, seat_id: int | None, seat_price_paid: int
) -> None:
    execute(
        "UPDATE passenger_seats SET seat_id = ?, seat_price_paid = ?"
        " WHERE booking_passenger_id = ? AND segment_id = ?",
        (seat_id, seat_price_paid, passenger_id, segment_id),
    )


def next_boarding_sequence(flight_id: int) -> int:
    """The next sequence number on a flight. Call inside a transaction."""
    current = fetch_value(
        "SELECT MAX(ps.boarding_sequence) FROM passenger_seats ps"
        " JOIN booking_segments s ON s.id = ps.segment_id WHERE s.flight_id = ?",
        (flight_id,),
    )
    return (current or 0) + 1


def mark_checked_in(
    passenger_id: int, segment_id: int, checked_in_at: str, sequence: int, group: int
) -> None:
    execute(
        "UPDATE passenger_seats SET checked_in_at = ?, boarding_sequence = ?, boarding_group = ?"
        " WHERE booking_passenger_id = ? AND segment_id = ? AND checked_in_at IS NULL",
        (checked_in_at, sequence, group, passenger_id, segment_id),
    )


def clear_check_in(segment_id: int) -> None:
    execute(
        "UPDATE passenger_seats SET checked_in_at = NULL, boarding_sequence = NULL,"
        " boarding_group = NULL WHERE segment_id = ?",
        (segment_id,),
    )


def manifest(flight_id: int) -> list[Row]:
    """Every passenger on a flight whose booking is still live."""
    return fetch_all(
        """
        SELECT p.id AS passenger_id, p.full_name, p.passenger_type, p.id_number,
               b.reference, b.status AS booking_status, seg.cabin, seg.fare_family,
               st.seat_code, ps.checked_in_at, ps.boarding_sequence, ps.boarding_group,
               (SELECT GROUP_CONCAT(e.name || CASE WHEN be.quantity > 1
                         THEN ' x' || be.quantity ELSE '' END, ', ')
                  FROM booking_extras be JOIN extras e ON e.code = be.extra_code
                 WHERE be.booking_passenger_id = p.id) AS extras
        FROM booking_segments seg
        JOIN bookings b ON b.id = seg.booking_id
        JOIN passenger_seats ps ON ps.segment_id = seg.id
        JOIN booking_passengers p ON p.id = ps.booking_passenger_id
        LEFT JOIN seats st ON st.id = ps.seat_id
        WHERE seg.flight_id = ? AND b.status <> 'Cancelled'
        ORDER BY st.id IS NULL, st.id, p.id
        """,
        (flight_id,),
    )
