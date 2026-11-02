"""Live flight status: estimated times, in-flight progress and airport boards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from sqlite3 import Row

from anga import clock
from anga.repositories import airports as airports_repo
from anga.repositories import flights as flights_repo
from anga.services.booking import flight_departure

BOARD_KINDS = ("departures", "arrivals")


@dataclass
class FlightStatus:
    flight: Row
    status: str
    delay_minutes: int
    gate: str | None
    estimated_departure: str
    estimated_arrival: str
    progress: int

    def as_dict(self) -> dict:
        flight = self.flight
        return {
            "flight_number": flight["flight_number"],
            "date": flight["departure_date"],
            "origin": flight["origin"],
            "origin_city": flight["origin_city"],
            "destination": flight["destination"],
            "destination_city": flight["destination_city"],
            "scheduled_departure": flight["departure_time"],
            "scheduled_arrival": flight["arrival_time"],
            "estimated_departure": self.estimated_departure,
            "estimated_arrival": self.estimated_arrival,
            "status": self.status,
            "delay_minutes": self.delay_minutes,
            "gate": self.gate,
            "progress": self.progress,
        }


def _shift(time_text: str, minutes: int) -> str:
    moment = datetime.strptime(time_text, "%H:%M") + timedelta(minutes=minutes)
    return moment.strftime("%H:%M")


def progress_percent(flight: Row, now: datetime) -> int:
    """How far along the route a flight is, for the progress line."""
    if flight["status"] == "Landed":
        return 100
    if flight["status"] != "Departed":
        return 0
    departed = flight_departure(flight) + timedelta(minutes=flight["delay_minutes"])
    elapsed = (now - departed) / timedelta(minutes=flight["duration_minutes"])
    return max(1, min(99, round(elapsed * 100)))


def describe(flight: Row, now: datetime | None = None) -> FlightStatus:
    now = now or clock.now()
    delay = flight["delay_minutes"]
    return FlightStatus(
        flight=flight,
        status=flight["status"],
        delay_minutes=delay,
        gate=flight["gate"],
        estimated_departure=_shift(flight["departure_time"], delay),
        estimated_arrival=_shift(flight["arrival_time"], delay),
        progress=progress_percent(flight, now),
    )


def by_number(flight_number: str, day: date) -> FlightStatus | None:
    flight = flights_repo.get_by_number(flight_number, day.isoformat())
    return describe(flight) if flight else None


def by_route(origin: str, destination: str, day: date) -> list[FlightStatus]:
    return [
        describe(flight)
        for flight in flights_repo.on_route_and_date(origin, destination, day.isoformat())
    ]


def board(airport: str, kind: str, day: date) -> list[FlightStatus]:
    """Today's departures or arrivals, in the order a terminal screen would show them."""
    rows = (
        flights_repo.arrivals_to(airport, day.isoformat())
        if kind == "arrivals"
        else flights_repo.departures_from(airport, day.isoformat())
    )
    return [describe(flight) for flight in rows]


def airport(code: str) -> Row | None:
    return airports_repo.get(code)
