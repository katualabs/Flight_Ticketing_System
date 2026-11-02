"""SQL for in-progress booking wizard state."""

from __future__ import annotations

import json

from anga.db import execute, fetch_value


def load(token: str) -> dict | None:
    data = fetch_value("SELECT data FROM booking_drafts WHERE token = ?", (token,))
    return json.loads(data) if data else None


def save(token: str, data: dict, updated_at: str) -> None:
    execute(
        "INSERT INTO booking_drafts (token, data, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT (token) DO UPDATE SET data = excluded.data,"
        " updated_at = excluded.updated_at",
        (token, json.dumps(data), updated_at),
    )


def delete(token: str) -> None:
    execute("DELETE FROM booking_drafts WHERE token = ?", (token,))


def delete_older_than(cutoff: str) -> None:
    execute("DELETE FROM booking_drafts WHERE updated_at < ?", (cutoff,))
