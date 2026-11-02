"""SQL for the simulated email outbox."""

from __future__ import annotations

from sqlite3 import Row

from anga.db import execute, fetch_all, fetch_one, fetch_value


def insert(recipient: str, subject: str, html_body: str, created_at: str) -> int:
    cursor = execute(
        "INSERT INTO outbox (recipient, subject, html_body, created_at) VALUES (?, ?, ?, ?)",
        (recipient, subject, html_body, created_at),
    )
    return cursor.lastrowid


def get(message_id: int) -> Row | None:
    return fetch_one("SELECT * FROM outbox WHERE id = ?", (message_id,))


def recent(limit: int, offset: int = 0) -> tuple[list[Row], int]:
    total = fetch_value("SELECT COUNT(*) FROM outbox")
    rows = fetch_all(
        "SELECT id, recipient, subject, created_at FROM outbox"
        " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return rows, total


def for_recipient(recipient: str) -> list[Row]:
    return fetch_all("SELECT * FROM outbox WHERE recipient = ? ORDER BY id DESC", (recipient,))
