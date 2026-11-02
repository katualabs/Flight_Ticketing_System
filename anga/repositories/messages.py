"""SQL for contact form messages."""

from __future__ import annotations

from sqlite3 import Row

from anga.db import execute, fetch_all, fetch_one, fetch_value


def insert(full_name: str, email: str, subject: str, body: str, created_at: str) -> int:
    cursor = execute(
        "INSERT INTO contact_messages (full_name, email, subject, body, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (full_name, email, subject, body, created_at),
    )
    return cursor.lastrowid


def get(message_id: int) -> Row | None:
    return fetch_one("SELECT * FROM contact_messages WHERE id = ?", (message_id,))


def inbox(limit: int, offset: int = 0) -> tuple[list[Row], int]:
    total = fetch_value("SELECT COUNT(*) FROM contact_messages")
    rows = fetch_all(
        "SELECT * FROM contact_messages ORDER BY is_read, created_at DESC, id DESC"
        " LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return rows, total


def unread_count() -> int:
    return fetch_value("SELECT COUNT(*) FROM contact_messages WHERE is_read = 0")


def set_read(message_id: int, is_read: bool) -> None:
    execute("UPDATE contact_messages SET is_read = ? WHERE id = ?", (int(is_read), message_id))


def save_reply_note(message_id: int, note: str) -> None:
    execute(
        "UPDATE contact_messages SET reply_note = ?, is_read = 1 WHERE id = ?", (note, message_id)
    )
