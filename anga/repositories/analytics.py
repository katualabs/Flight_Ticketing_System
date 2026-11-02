"""Reporting SQL for the operations dashboard."""

from __future__ import annotations

from sqlite3 import Row

from anga.db import fetch_all, fetch_one, fetch_value

NET_AMOUNT = "CASE p.kind WHEN 'charge' THEN p.amount ELSE -p.amount END"


def revenue_since(start: str, end: str) -> int:
    """Net money taken between two ISO timestamps: charges minus refunds."""
    value = fetch_value(
        f"SELECT COALESCE(SUM({NET_AMOUNT}), 0) FROM payments p"
        " WHERE p.status = 'succeeded' AND p.created_at >= ? AND p.created_at < ?",
        (start, end),
    )
    return int(value)


def revenue_by_day(start: str, end: str) -> dict[str, int]:
    rows = fetch_all(
        f"SELECT substr(p.created_at, 1, 10) AS day, SUM({NET_AMOUNT}) AS amount"
        " FROM payments p WHERE p.status = 'succeeded' AND p.created_at >= ? AND p.created_at < ?"
        " GROUP BY day",
        (start, end),
    )
    return {row["day"]: row["amount"] for row in rows}


def bookings_since(start: str) -> int:
    return fetch_value("SELECT COUNT(*) FROM bookings WHERE created_at >= ?", (start,))


def pending_payments() -> Row:
    return fetch_one(
        "SELECT COUNT(*) AS count, COALESCE(SUM(total), 0) AS amount"
        " FROM bookings WHERE status = 'Pending'"
    )


def top_routes(start: str, limit: int) -> list[Row]:
    return fetch_all(
        """
        SELECT f.origin, f.destination, SUM(s.fare_paid) AS revenue, COUNT(*) AS segments
        FROM booking_segments s
        JOIN bookings b ON b.id = s.booking_id
        JOIN flights f ON f.id = s.flight_id
        WHERE b.status = 'Confirmed' AND b.created_at >= ?
        GROUP BY f.origin, f.destination
        ORDER BY revenue DESC LIMIT ?
        """,
        (start, limit),
    )


def cabin_mix(start: str) -> list[Row]:
    return fetch_all(
        """
        SELECT s.cabin, COUNT(*) AS passengers
        FROM passenger_seats ps
        JOIN booking_segments s ON s.id = ps.segment_id
        JOIN bookings b ON b.id = s.booking_id
        WHERE b.status = 'Confirmed' AND b.created_at >= ?
        GROUP BY s.cabin
        """,
        (start,),
    )


def load_between(start: str, end: str) -> Row:
    return fetch_one(
        """
        SELECT COALESCE(SUM(fa.total_seats), 0) AS total,
               COALESCE(SUM(fa.available_seats), 0) AS available
        FROM fares fa JOIN flights f ON f.id = fa.flight_id
        WHERE f.departure_date BETWEEN ? AND ? AND f.status <> 'Cancelled'
        """,
        (start, end),
    )


def departures_with_load(departure_date: str) -> list[Row]:
    return fetch_all(
        """
        SELECT f.id, f.flight_number, f.origin, f.destination, f.departure_time, f.status,
               f.delay_minutes, f.gate,
               SUM(fa.total_seats) AS total, SUM(fa.available_seats) AS available
        FROM flights f JOIN fares fa ON fa.flight_id = f.id
        WHERE f.departure_date = ?
        GROUP BY f.id ORDER BY f.departure_time
        """,
        (departure_date,),
    )
