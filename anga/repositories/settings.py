"""SQL for the key/value settings table."""

from __future__ import annotations

from anga.db import execute, fetch_all, fetch_value


def get(key: str, default: str | None = None) -> str | None:
    value = fetch_value("SELECT value FROM settings WHERE key = ?", (key,))
    return default if value is None else value


def put(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def all_settings() -> dict[str, str]:
    return {row["key"]: row["value"] for row in fetch_all("SELECT key, value FROM settings")}
