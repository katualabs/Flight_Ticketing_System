"""Builders shared across test modules."""

from __future__ import annotations

from datetime import date, timedelta

from anga import db
from anga.repositories import fares as fares_repo
from anga.repositories import flights as flights_repo
from anga.services import booking

TODAY = date(2026, 3, 2)


def future_date(days: int = 7) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def get_flight(number: str = "AN101", days: int = 7):
    return flights_repo.get_by_number(number, future_date(days))


def get_fare(number: str = "AN101", days: int = 7, cabin: str = "Economy", family: str = "Classic"):
    return fares_repo.get(get_flight(number, days)["id"], cabin, family)


def make_draft(
    number: str = "AN101",
    days: int = 7,
    cabin: str = "Economy",
    family: str = "Classic",
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    return_number: str | None = None,
    return_days: int = 10,
) -> dict:
    """A complete draft, as if the passenger and contact steps were already done."""
    outbound = get_fare(number, days, cabin, family)
    inbound = get_fare(return_number, return_days, cabin, family) if return_number else None
    draft = booking.new_draft(
        outbound["id"], inbound["id"] if inbound else None, adults, children, infants
    )
    draft["passengers"] = [
        {"full_name": f"Test Passenger{chr(65 + i)}", "id_number": f"ID{i:06d}"}
        for i in range(adults + children + infants)
    ]
    draft["contact"] = {"email": "traveller@example.com", "phone": "+254712345678"}
    return draft


def make_booking(**overrides):
    return booking.create_booking(make_draft(**overrides))


def free_seat_count(flight_id: int, cabin: str = "Economy") -> int:
    return db.fetch_value(
        "SELECT COUNT(*) FROM seats WHERE flight_id = ? AND cabin = ? AND blocked = 0"
        " AND booking_passenger_id IS NULL",
        (flight_id, cabin),
    )
