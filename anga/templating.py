"""Template helpers: money, dates and the context every page expects."""

from __future__ import annotations

from datetime import date, datetime

from flask import Flask, g, has_request_context, session

from anga import clock, i18n


def format_ksh(amount: int | None) -> str:
    return f"KSh {int(amount or 0):,}"


def format_money(amount: int | None) -> str:
    """Show an amount in the visitor's display currency.

    USD is display-only: bookings are always charged in shillings, so this
    never feeds back into any calculation.
    """
    if has_request_context() and session.get("currency") == "USD":
        rate = g.get("usd_rate") or _load_usd_rate()
        return f"US$ {round(int(amount or 0) / rate):,}"
    return format_ksh(amount)


def _load_usd_rate() -> float:
    from anga.services.preferences import usd_rate

    g.usd_rate = usd_rate()
    return g.usd_rate


def format_date(value: str | date | None, pattern: str = "%a %d %b %Y") -> str:
    if not value:
        return ""
    parsed = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return parsed.strftime(pattern)


def format_datetime(value: str | datetime | None, pattern: str = "%d %b %Y, %H:%M") -> str:
    if not value:
        return ""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.strftime(pattern)


def format_duration(minutes: int | None) -> str:
    hours, mins = divmod(int(minutes or 0), 60)
    if not hours:
        return f"{mins}m"
    return f"{hours}h {mins:02d}m" if mins else f"{hours}h"


def mask_id(value: str | None) -> str:
    """Show only the end of an ID number on anything that might be seen or printed."""
    text = value or ""
    return "\u2022" * max(len(text) - 3, 3) + text[-3:]


STATUS_BADGES = {
    "Scheduled": "badge-info",
    "On time": "badge-success",
    "Delayed": "badge-warning",
    "Boarding": "badge-info",
    "Departed": "badge-info",
    "Landed": "badge-success",
    "Cancelled": "badge-danger",
    "Pending": "badge-warning",
    "Confirmed": "badge-success",
    "succeeded": "badge-success",
    "failed": "badge-danger",
    "initiated": "badge-warning",
}


def status_badge(status: str | None) -> str:
    return STATUS_BADGES.get(status or "", "")


def init_app(app: Flask) -> None:
    app.jinja_env.filters.update(
        money=format_money,
        ksh=format_ksh,
        date=format_date,
        datetime=format_datetime,
        duration=format_duration,
        status_badge=status_badge,
        mask_id=mask_id,
    )
    app.jinja_env.globals.update(t=i18n.t, today=clock.today)
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    @app.context_processor
    def inject_globals() -> dict:
        return {
            "current_lang": i18n.current_language(),
            "current_currency": session.get("currency", "KES"),
        }
