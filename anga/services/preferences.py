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
