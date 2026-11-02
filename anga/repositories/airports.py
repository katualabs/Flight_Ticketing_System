"""SQL for airports and aircraft types."""

from __future__ import annotations

from collections.abc import Iterable
from sqlite3 import Row

from anga.db import execute_many, fetch_all, fetch_one


def insert_many(rows: Iterable[tuple]) -> None:
    execute_many(
        "INSERT INTO airports (code, city, name, country, timezone, lat, lng, is_coastal)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def all_airports() -> list[Row]:
    return fetch_all("SELECT * FROM airports ORDER BY city")


def get(code: str) -> Row | None:
    return fetch_one("SELECT * FROM airports WHERE code = ?", (code,))


def insert_aircraft(rows: Iterable[tuple]) -> None:
    execute_many("INSERT INTO aircraft_types (code, name, layout) VALUES (?, ?, ?)", rows)


def all_aircraft() -> list[Row]:
    return fetch_all("SELECT * FROM aircraft_types ORDER BY name")


def get_aircraft(code: str) -> Row | None:
    return fetch_one("SELECT * FROM aircraft_types WHERE code = ?", (code,))
