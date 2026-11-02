"""SQL for price-drop watches."""

from __future__ import annotations

from sqlite3 import Row

from anga.db import execute, fetch_all

WATCH_SELECT = """
    SELECT w.*, o.city AS origin_city, d.city AS destination_city
    FROM price_watches w
    JOIN airports o ON o.code = w.origin
    JOIN airports d ON d.code = w.destination
"""


def upsert(
    user_id: int,
    origin: str,
    destination: str,
    travel_date: str,
    cabin: str,
    seen_price: int,
    created_at: str,
) -> None:
    """Watching the same trip again restarts the watch from the current price."""
    execute(
        "INSERT INTO price_watches (user_id, origin, destination, travel_date, cabin, seen_price,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (user_id, origin, destination, travel_date, cabin) DO UPDATE SET"
        " seen_price = excluded.seen_price, alert_price = NULL, alerted_at = NULL, dismissed = 0",
        (user_id, origin, destination, travel_date, cabin, seen_price, created_at),
    )


def for_user(user_id: int) -> list[Row]:
    return fetch_all(
        f"{WATCH_SELECT} WHERE w.user_id = ? AND w.dismissed = 0 ORDER BY w.travel_date",
        (user_id,),
    )


def pending(today: str, user_id: int | None = None) -> list[Row]:
    """Future watches that have not alerted yet, optionally for just one customer."""
    query = f"{WATCH_SELECT} WHERE w.alerted_at IS NULL AND w.dismissed = 0 AND w.travel_date >= ?"
    params: list = [today]
    if user_id is not None:
        query += " AND w.user_id = ?"
        params.append(user_id)
    return fetch_all(query, params)


def mark_alerted(watch_id: int, price: int, moment: str) -> None:
    execute(
        "UPDATE price_watches SET alert_price = ?, alerted_at = ? WHERE id = ?",
        (price, moment, watch_id),
    )


def dismiss(user_id: int, watch_id: int) -> bool:
    cursor = execute(
        "UPDATE price_watches SET dismissed = 1 WHERE id = ? AND user_id = ?",
        (watch_id, user_id),
    )
    return cursor.rowcount == 1
