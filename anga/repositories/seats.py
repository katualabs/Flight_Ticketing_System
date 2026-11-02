"""SQL for physical seats. Claims are guarded so a seat can only be taken once."""

from __future__ import annotations

from collections.abc import Iterable
from sqlite3 import Row

from anga.db import execute, execute_many, fetch_all, fetch_one


def insert_many(rows: Iterable[tuple]) -> None:
    execute_many(
        "INSERT INTO seats (flight_id, seat_code, cabin, is_window, is_aisle, extra_legroom,"
        " price_extra, blocked) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def for_flight(flight_id: int) -> list[Row]:
    return fetch_all("SELECT * FROM seats WHERE flight_id = ? ORDER BY id", (flight_id,))


def get(flight_id: int, seat_code: str) -> Row | None:
    return fetch_one(
        "SELECT * FROM seats WHERE flight_id = ? AND seat_code = ?", (flight_id, seat_code)
    )


def get_by_id(seat_id: int) -> Row | None:
    return fetch_one("SELECT * FROM seats WHERE id = ?", (seat_id,))


def free_in_cabin(flight_id: int, cabin: str) -> list[Row]:
    """Free seats, free-of-charge ones first so auto-assignment never upsells."""
    return fetch_all(
        "SELECT * FROM seats"
        " WHERE flight_id = ? AND cabin = ? AND blocked = 0 AND booking_passenger_id IS NULL"
        " ORDER BY price_extra, id",
        (flight_id, cabin),
    )


def block(seat_ids: Iterable[int]) -> None:
    """Take seats out of sale without a passenger, as for a group or crew block."""
    execute_many("UPDATE seats SET blocked = 1 WHERE id = ?", [(seat_id,) for seat_id in seat_ids])


def claim(seat_id: int, passenger_id: int) -> bool:
    """Assign a seat only if it is still free."""
    cursor = execute(
        "UPDATE seats SET booking_passenger_id = ?"
        " WHERE id = ? AND blocked = 0 AND booking_passenger_id IS NULL",
        (passenger_id, seat_id),
    )
    return cursor.rowcount == 1


def release(seat_id: int) -> None:
    execute("UPDATE seats SET booking_passenger_id = NULL WHERE id = ?", (seat_id,))
