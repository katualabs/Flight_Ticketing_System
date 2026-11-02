"""Visitor display preferences backed by admin-set values."""

from __future__ import annotations

from anga.repositories import settings as settings_repo

DEFAULT_USD_RATE = 129.0


def usd_rate() -> float:
    """Shillings per US dollar, falling back safely if the setting is bad."""
    try:
        rate = float(settings_repo.get("usd_rate", str(DEFAULT_USD_RATE)))
    except ValueError:
        return DEFAULT_USD_RATE
    return rate if rate > 0 else DEFAULT_USD_RATE


def _int_setting(key: str, default: int) -> int:
    try:
        return int(settings_repo.get(key, str(default)))
    except ValueError:
        return default


def cancellation_hours() -> int:
    return _int_setting("cancellation_hours", 3)


def checkin_open_hours() -> int:
    return _int_setting("checkin_open_hours", 48)


def checkin_close_hours() -> int:
    return _int_setting("checkin_close_hours", 1)
