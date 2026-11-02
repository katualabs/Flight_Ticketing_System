"""SQL for fare buckets. All inventory changes are guarded updates."""

from __future__ import annotations

from collections.abc import Iterable
from sqlite3 import Row

from anga.db import execute, execute_many, fetch_all, fetch_one

# Load is a property of the cabin, not the bucket, so every fare row carries its
# cabin's totals to feed demand pricing.
FARE_SELECT = """
    SELECT fa.*,
           (SELECT SUM(x.total_seats) FROM fares x
             WHERE x.flight_id = fa.flight_id AND x.cabin = fa.cabin) AS cabin_total,
           (SELECT SUM(x.available_seats) FROM fares x
             WHERE x.flight_id = fa.flight_id AND x.cabin = fa.cabin) AS cabin_available
    FROM fares fa
"""


def insert_many(rows: Iterable[tuple]) -> None:
    execute_many(
        "INSERT INTO fares (flight_id, cabin, fare_family, price, total_seats, available_seats)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )


def for_flight(flight_id: int) -> list[Row]:
    return fetch_all(
        f"{FARE_SELECT} WHERE fa.flight_id = ?"
        " ORDER BY CASE fa.cabin WHEN 'Economy' THEN 0 WHEN 'Business' THEN 1 ELSE 2 END, fa.price",
        (flight_id,),
    )


def get(flight_id: int, cabin: str, family: str) -> Row | None:
    return fetch_one(
        f"{FARE_SELECT} WHERE fa.flight_id = ? AND fa.cabin = ? AND fa.fare_family = ?",
        (flight_id, cabin, family),
    )


def get_by_id(fare_id: int) -> Row | None:
    return fetch_one(f"{FARE_SELECT} WHERE fa.id = ?", (fare_id,))


def in_date_range(origin: str, destination: str, start: str, end: str, cabin: str) -> list[Row]:
    """Bookable fares on a route between two dates, for the fare calendar."""
    return fetch_all(
        """
        SELECT fa.*, f.departure_date, f.flight_number, f.departure_time,
               c.cabin_total, c.cabin_available
        FROM flights f
        JOIN fares fa ON fa.flight_id = f.id
        JOIN (SELECT flight_id, cabin, SUM(total_seats) AS cabin_total,
                     SUM(available_seats) AS cabin_available
              FROM fares GROUP BY flight_id, cabin) c
          ON c.flight_id = fa.flight_id AND c.cabin = fa.cabin
        WHERE f.origin = ? AND f.destination = ? AND f.departure_date BETWEEN ? AND ?
          AND f.status <> 'Cancelled' AND fa.cabin = ? AND fa.available_seats > 0
        """,
        (origin, destination, start, end, cabin),
    )


def economy_from_origin(origin: str, start: str, end: str) -> list[Row]:
    """Economy fares leaving ``origin``, used for destination cards and deals."""
    return fetch_all(
        """
        SELECT fa.*, f.departure_date, f.flight_number, f.destination,
               d.city AS destination_city, d.country AS destination_country,
               c.cabin_total, c.cabin_available
        FROM flights f
        JOIN airports d ON d.code = f.destination
        JOIN fares fa ON fa.flight_id = f.id
        JOIN (SELECT flight_id, cabin, SUM(total_seats) AS cabin_total,
                     SUM(available_seats) AS cabin_available
              FROM fares WHERE cabin = 'Economy' GROUP BY flight_id, cabin) c
          ON c.flight_id = fa.flight_id AND c.cabin = fa.cabin
        WHERE f.origin = ? AND f.departure_date BETWEEN ? AND ?
          AND f.status <> 'Cancelled' AND fa.cabin = 'Economy' AND fa.available_seats > 0
        """,
        (origin, start, end),
    )


def take_inventory(fare_id: int, quantity: int) -> bool:
    """Decrement a bucket only if enough seats remain.

    The condition lives in the UPDATE itself, so two simultaneous requests can
    never both take the last seat regardless of what they read beforehand.
    """
    cursor = execute(
        "UPDATE fares SET available_seats = available_seats - ?"
        " WHERE id = ? AND available_seats >= ?",
        (quantity, fare_id, quantity),
    )
    return cursor.rowcount == 1


def release_inventory(flight_id: int, cabin: str, family: str, quantity: int) -> None:
    execute(
        "UPDATE fares SET available_seats = MIN(total_seats, available_seats + ?)"
        " WHERE flight_id = ? AND cabin = ? AND fare_family = ?",
        (quantity, flight_id, cabin, family),
    )


def update(fare_id: int, price: int, total_seats: int, available_seats: int) -> None:
    execute(
        "UPDATE fares SET price = ?, total_seats = ?, available_seats = ? WHERE id = ?",
        (price, total_seats, available_seats, fare_id),
    )
