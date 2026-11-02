"""RFC 5545 calendar files for an itinerary. Pure: no Flask, no database."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class CalendarFlight:
    flight_number: str
    origin: str
    origin_city: str
    destination: str
    destination_city: str
    departure_utc: datetime
    duration_minutes: int


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    """Lines over 75 octets must be folded; continuation lines begin with a space."""
    chunks = [line[i : i + 72] for i in range(0, len(line), 72)]
    return "\r\n ".join(chunks)


def build_ics(reference: str, flights: Iterable[CalendarFlight], stamped_at: datetime) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Anga Air//Booking Platform//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for flight in flights:
        arrival = flight.departure_utc + timedelta(minutes=flight.duration_minutes)
        summary = f"{flight.flight_number} {flight.origin_city} to {flight.destination_city}"
        description = f"Anga Air booking {reference}. Demo project: this flight is fictional."
        lines += [
            "BEGIN:VEVENT",
            f"UID:{reference}-{flight.flight_number}-{_stamp(flight.departure_utc)}@anga.example",
            f"DTSTAMP:{_stamp(stamped_at)}",
            f"DTSTART:{_stamp(flight.departure_utc)}",
            f"DTEND:{_stamp(arrival)}",
            f"SUMMARY:{_escape(summary)}",
            f"LOCATION:{_escape(f'{flight.origin_city} ({flight.origin})')}",
            f"DESCRIPTION:{_escape(description)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
