"""SQL for the catalogue of purchasable extras."""

from __future__ import annotations

from collections.abc import Iterable
from sqlite3 import Row

from anga.db import execute_many, fetch_all


def insert_many(rows: Iterable[tuple]) -> None:
    execute_many("INSERT INTO extras (code, name, price, type) VALUES (?, ?, ?, ?)", rows)


def active() -> list[Row]:
    return fetch_all("SELECT * FROM extras WHERE active = 1 ORDER BY type, price")
