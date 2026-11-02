"""SQL for flights and the route templates they are generated from."""

from __future__ import annotations

from collections.abc import Iterable
from sqlite3 import Row

from anga.db import execute, execute_many, fetch_all, fetch_one, fetch_value

FLIGHT_SELECT = """
    SELECT f.*,
           o.city AS origin_city, o.name AS origin_name, o.timezone AS origin_tz,
           d.city AS destination_city, d.name AS destination_name, d.timezone AS destination_tz,
           o.is_coastal AS origin_coastal, d.is_coastal AS destination_coastal,
           a.name AS aircraft_name
    FROM flights f
    JOIN airports o ON o.code = f.origin
    JOIN airports d ON d.code = f.destination
    JOIN aircraft_types a ON a.code = f.aircraft_code
"""


def insert_route_templates(rows: Iterable[tuple]) -> None:
    execute_many(
        "INSERT INTO route_schedules (flight_number, origin, destination, departure_time,"
        " duration_minutes, aircraft_code, base_fare, weekdays) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def route_templates() -> list[Row]:
    return fetch_all(
        "SELECT r.*, o.timezone AS origin_tz, d.timezone AS destination_tz,"
        " o.city AS origin_city, d.city AS destination_city"
        " FROM route_schedules r"
        " JOIN airports o ON o.code = r.origin"
        " JOIN airports d ON d.code = r.destination"
        " WHERE r.active = 1 ORDER BY r.flight_number"
    )


def get_route_template(flight_number: str) -> Row | None:
    return fetch_one(
        "SELECT r.*, o.timezone AS origin_tz, d.timezone AS destination_tz"
        " FROM route_schedules r"
        " JOIN airports o ON o.code = r.origin"
        " JOIN airports d ON d.code = r.destination"
        " WHERE r.flight_number = ?",
        (flight_number,),
    )


def distinct_routes() -> list[Row]:
    """One row per origin/destination pair served, with coordinates for the map."""
    return fetch_all(
        "SELECT r.origin, r.destination, MIN(r.base_fare) AS base_fare,"
        " o.city AS origin_city, d.city AS destination_city,"
        " o.lat AS origin_lat, o.lng AS origin_lng, d.lat AS destination_lat,"
        " d.lng AS destination_lng"
        " FROM route_schedules r"
        " JOIN airports o ON o.code = r.origin"
        " JOIN airports d ON d.code = r.destination"
        " WHERE r.active = 1 GROUP BY r.origin, r.destination"
    )


def insert(
    flight_number: str,
    departure_date: str,
    origin: str,
    destination: str,
    departure_time: str,
    arrival_time: str,
    duration_minutes: int,
    aircraft_code: str,
) -> int | None:
    """Insert a flight; returns None if that number already flies on that date."""
    cursor = execute(
        "INSERT OR IGNORE INTO flights (flight_number, departure_date, origin, destination,"
        " departure_time, arrival_time, duration_minutes, aircraft_code)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            flight_number,
            departure_date,
            origin,
            destination,
            departure_time,
            arrival_time,
            duration_minutes,
            aircraft_code,
        ),
    )
    return cursor.lastrowid if cursor.rowcount else None


def get(flight_id: int) -> Row | None:
    return fetch_one(f"{FLIGHT_SELECT} WHERE f.id = ?", (flight_id,))


def get_by_number(flight_number: str, departure_date: str) -> Row | None:
    return fetch_one(
        f"{FLIGHT_SELECT} WHERE f.flight_number = ? AND f.departure_date = ?",
        (flight_number, departure_date),
    )


def find(origin: str, destination: str, departure_date: str) -> list[Row]:
    return fetch_all(
        f"{FLIGHT_SELECT} WHERE f.origin = ? AND f.destination = ? AND f.departure_date = ?"
        " AND f.status <> 'Cancelled' ORDER BY f.departure_time",
        (origin, destination, departure_date),
    )


def on_route_and_date(origin: str, destination: str, departure_date: str) -> list[Row]:
    """Same as ``find`` but includes cancelled flights, for the status page."""
    return fetch_all(
        f"{FLIGHT_SELECT} WHERE f.origin = ? AND f.destination = ? AND f.departure_date = ?"
        " ORDER BY f.departure_time",
        (origin, destination, departure_date),
    )


def on_date(departure_date: str) -> list[Row]:
    return fetch_all(
        f"{FLIGHT_SELECT} WHERE f.departure_date = ? ORDER BY f.departure_time",
        (departure_date,),
    )


def departures_from(airport: str, departure_date: str) -> list[Row]:
    return fetch_all(
        f"{FLIGHT_SELECT} WHERE f.origin = ? AND f.departure_date = ? ORDER BY f.departure_time",
        (airport, departure_date),
    )


def arrivals_to(airport: str, departure_date: str) -> list[Row]:
    return fetch_all(
        f"{FLIGHT_SELECT} WHERE f.destination = ? AND f.departure_date = ? ORDER BY f.arrival_time",
        (airport, departure_date),
    )


def search_admin(
    query: str | None,
    origin: str | None,
    departure_date: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Row], int]:
    """Filtered, paginated flight list for the ops console."""
    clauses, params = [], []
    if query:
        clauses.append("(f.flight_number LIKE ? OR f.origin LIKE ? OR f.destination LIKE ?)")
        params += [f"%{query}%"] * 3
    if origin:
        clauses.append("f.origin = ?")
        params.append(origin)
    if departure_date:
        clauses.append("f.departure_date = ?")
        params.append(departure_date)
    if status:
        clauses.append("f.status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = fetch_value(f"SELECT COUNT(*) FROM flights f {where}", params)
    rows = fetch_all(
        f"{FLIGHT_SELECT} {where} ORDER BY f.departure_date, f.departure_time LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    return rows, total


def update_status(flight_id: int, status: str, delay_minutes: int, gate: str | None) -> None:
    execute(
        "UPDATE flights SET status = ?, delay_minutes = ?, gate = ? WHERE id = ?",
        (status, delay_minutes, gate, flight_id),
    )


def update_times(
    flight_id: int, departure_time: str, arrival_time: str, duration_minutes: int
) -> None:
    execute(
        "UPDATE flights SET departure_time = ?, arrival_time = ?, duration_minutes = ?"
        " WHERE id = ?",
        (departure_time, arrival_time, duration_minutes, flight_id),
    )


def delete(flight_id: int) -> None:
    execute("DELETE FROM flights WHERE id = ?", (flight_id,))


def land_stale_flights(before_date: str) -> None:
    """Flights on past days that nobody updated have, in practice, landed."""
    execute(
        "UPDATE flights SET status = 'Landed'"
        " WHERE departure_date < ? AND status NOT IN ('Landed', 'Cancelled')",
        (before_date,),
    )
