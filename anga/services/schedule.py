"""Turns route templates into dated flights with fare buckets and seat maps."""

from __future__ import annotations

import json
import random
from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta
from sqlite3 import Row

from anga import clock
from anga.db import transaction
from anga.repositories import airports as airports_repo
from anga.repositories import fares as fares_repo
from anga.repositories import flights as flights_repo
from anga.repositories import seats as seats_repo
from anga.repositories import settings as settings_repo
from anga.services import pricing

BUCKET_SHARE = {"Lite": 0.4, "Classic": 0.4, "Flex": 0.2}
GENERATED_THROUGH_KEY = "schedule_generated_through"

EXIT_ROW_PRICE = 1500
FRONT_ROW_PRICE = 600
FRONT_ROW_COUNT = 3


def arrival_time(departure_time: str, duration: int, origin_tz: str, destination_tz: str) -> str:
    """Local arrival time at the destination, accounting for timezone differences."""
    departure = datetime.strptime(departure_time, "%H:%M")
    offsets = clock.TIMEZONE_OFFSETS
    shift = offsets.get(destination_tz, 180) - offsets.get(origin_tz, 180)
    return (departure + timedelta(minutes=duration + shift)).strftime("%H:%M")


def partition_seats(total: int) -> dict[str, int]:
    """Split a cabin between fare families so the buckets always sum to ``total``."""
    lite = round(total * BUCKET_SHARE["Lite"])
    flex = round(total * BUCKET_SHARE["Flex"])
    return {"Lite": lite, "Classic": total - lite - flex, "Flex": flex}


def layout_seats(layout: dict) -> list[dict]:
    """Expand an aircraft layout into individual seats with their attributes."""
    seats = []
    for cabin in layout["cabins"]:
        letters = [c for c in cabin["columns"] if c != "|"]
        aisles = _aisle_letters(cabin["columns"])
        exit_rows = set(cabin.get("exit_rows", []))
        first_row = cabin["first_row"]
        for row in range(first_row, cabin["last_row"] + 1):
            if row in cabin.get("skip_rows", []):
                continue
            for letter in letters:
                seats.append(
                    {
                        "code": f"{row}{letter}",
                        "cabin": cabin["name"],
                        "is_window": letter in (letters[0], letters[-1]),
                        "is_aisle": letter in aisles,
                        "extra_legroom": row in exit_rows,
                        "price_extra": _seat_price(cabin["name"], row, first_row, exit_rows),
                    }
                )
    return seats


def _aisle_letters(columns: list[str]) -> set[str]:
    aisles = set()
    for index, column in enumerate(columns):
        if column == "|":
            aisles.update((columns[index - 1], columns[index + 1]))
    return aisles


def _seat_price(cabin: str, row: int, first_row: int, exit_rows: set[int]) -> int:
    if cabin != "Economy":
        return 0
    if row in exit_rows:
        return EXIT_ROW_PRICE
    return FRONT_ROW_PRICE if row < first_row + FRONT_ROW_COUNT else 0


def create_flight(
    flight_number: str,
    departure_date: date,
    origin: str,
    destination: str,
    departure_time: str,
    duration: int,
    aircraft_code: str,
    base_fare: int,
    origin_tz: str,
    destination_tz: str,
    prefill: float = 0.0,
) -> int | None:
    """Create one flight with its fares and seats; None if it already exists."""
    aircraft = airports_repo.get_aircraft(aircraft_code)
    flight_id = flights_repo.insert(
        flight_number,
        departure_date.isoformat(),
        origin,
        destination,
        departure_time,
        arrival_time(departure_time, duration, origin_tz, destination_tz),
        duration,
        aircraft_code,
    )
    if flight_id is None:
        return None
    seats = layout_seats(json.loads(aircraft["layout"]))
    rng = random.Random(f"{flight_number}-{departure_date}")
    fare_rows, seat_rows = [], []
    for cabin in pricing.CABINS:
        cabin_seats = [seat for seat in seats if seat["cabin"] == cabin]
        if not cabin_seats:
            continue
        taken = rng.sample(cabin_seats, round(len(cabin_seats) * prefill))
        for seat in taken:
            seat["blocked"] = True
        buckets = partition_seats(len(cabin_seats))
        sold = _spread_sold(buckets, len(taken))
        fare_rows += [
            (
                flight_id,
                cabin,
                family,
                pricing.base_price(base_fare, cabin, family),
                total,
                total - sold[family],
            )
            for family, total in buckets.items()
        ]
        seat_rows += [
            (
                flight_id,
                seat["code"],
                seat["cabin"],
                int(seat["is_window"]),
                int(seat["is_aisle"]),
                int(seat["extra_legroom"]),
                seat["price_extra"],
                int(seat.get("blocked", False)),
            )
            for seat in cabin_seats
        ]
    fares_repo.insert_many(fare_rows)
    seats_repo.insert_many(seat_rows)
    return flight_id


def _spread_sold(buckets: dict[str, int], sold: int) -> dict[str, int]:
    """Distribute already-sold seats across buckets, in proportion to their size."""
    total = sum(buckets.values())
    result = {family: min(size, round(sold * size / total)) for family, size in buckets.items()}
    remainder = sold - sum(result.values())
    for family, size in buckets.items():
        step = (
            min(remainder, size - result[family])
            if remainder > 0
            else max(remainder, -result[family])
        )
        result[family] += step
        remainder -= step
    return result


def fill_cabin(flight_id: int, cabin: str, leave_free: int) -> None:
    """Sell a cabin down to its last few seats, keeping seats and buckets in step."""
    free = seats_repo.free_in_cabin(flight_id, cabin)
    seats_repo.block(seat["id"] for seat in free[leave_free:])
    remaining = leave_free
    for fare in fares_repo.for_flight(flight_id):
        if fare["cabin"] != cabin:
            continue
        keep = min(remaining, fare["total_seats"])
        fares_repo.update(fare["id"], fare["price"], fare["total_seats"], keep)
        remaining -= keep


def prefill_for(flight_number: str, day: date, today: date) -> float:
    """A plausible load so seat maps and demand pricing look alive.

    Flights closer to departure are fuller, with per-flight variation so that
    some cross the demand-pricing thresholds and others do not.
    """
    rng = random.Random(f"load-{flight_number}-{day}")
    days_out = (day - today).days
    if days_out <= 3:
        return rng.uniform(0.45, 0.8)
    if days_out <= 14:
        return rng.uniform(0.2, 0.7)
    return rng.uniform(0.05, 0.4)


def generate_for_template(template: Row, day: date, today: date) -> int | None:
    if str(day.isoweekday()) not in template["weekdays"]:
        return None
    return create_flight(
        template["flight_number"],
        day,
        template["origin"],
        template["destination"],
        template["departure_time"],
        template["duration_minutes"],
        template["aircraft_code"],
        template["base_fare"],
        template["origin_tz"],
        template["destination_tz"],
        prefill=prefill_for(template["flight_number"], day, today),
    )


def top_up(today: date, horizon_days: int) -> int:
    """Extend the schedule to ``today + horizon``, generating only unseen dates.

    A high-water mark rather than a "does it exist" check is what stops flights
    an admin deleted from reappearing on the next start.
    """
    last_day = today + timedelta(days=horizon_days)
    marker = settings_repo.get(GENERATED_THROUGH_KEY)
    start = date.fromisoformat(marker) + timedelta(days=1) if marker else today
    if start > last_day:
        return 0
    created = 0
    templates = flights_repo.route_templates()
    with transaction():
        for day in _date_range(start, last_day):
            for template in templates:
                if generate_for_template(template, day, today):
                    created += 1
        settings_repo.put(GENERATED_THROUGH_KEY, last_day.isoformat())
    return created


def generate_history(today: date, days: int, flight_numbers: Iterable[str]) -> None:
    """Create a few past flights so demo bookings have somewhere to have flown."""
    with transaction():
        for number in flight_numbers:
            template = flights_repo.get_route_template(number)
            for offset in range(1, days + 1):
                generate_for_template(template, today - timedelta(days=offset), today)


def _date_range(start: date, end: date) -> Iterator[date]:
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)


def bulk_generate(flight_number: str, start: date, end: date, weekdays: str) -> tuple[int, int]:
    """Create a route's flights over a date range. Returns (created, skipped)."""
    template = flights_repo.get_route_template(flight_number)
    created = skipped = 0
    with transaction():
        for day in _date_range(start, end):
            if str(day.isoweekday()) not in weekdays:
                continue
            flight_id = create_flight(
                template["flight_number"],
                day,
                template["origin"],
                template["destination"],
                template["departure_time"],
                template["duration_minutes"],
                template["aircraft_code"],
                template["base_fare"],
                template["origin_tz"],
                template["destination_tz"],
            )
            if flight_id:
                created += 1
            else:
                skipped += 1
    return created, skipped


def advance_board(now: datetime) -> None:
    """Move today's and tomorrow's flights along with the clock.

    Statuses follow from the time, so the board stays alive at any hour with no
    background worker. Flights that staff have set by hand are left untouched.
    """
    today = now.date()
    with transaction():
        flights_repo.land_stale_flights(today.isoformat())
        dates = (today.isoformat(), (today + timedelta(days=1)).isoformat())
        for flight in flights_repo.simulated_on_dates(dates):
            status, delay, gate = _simulated_status(flight, now)
            if (status, delay, gate) != (flight["status"], flight["delay_minutes"], flight["gate"]):
                flights_repo.update_simulated_status(flight["id"], status, delay, gate)


def _simulated_status(flight: Row, now: datetime) -> tuple[str, int, str]:
    rng = random.Random(f"status-{flight['flight_number']}-{flight['departure_date']}")
    gate = f"{rng.choice('ABC')}{rng.randint(1, 12)}"
    departure = datetime.fromisoformat(f"{flight['departure_date']}T{flight['departure_time']}")
    departure = clock.local_to_network(departure, flight["origin_tz"])
    delay = rng.choice((25, 40, 55, 90)) if rng.random() < 0.22 else 0
    departs = departure + timedelta(minutes=delay)
    lands = departs + timedelta(minutes=flight["duration_minutes"])
    if now >= lands:
        return "Landed", delay, gate
    if now >= departs:
        return "Departed", delay, gate
    if now >= departs - timedelta(minutes=40):
        return "Boarding", delay, gate
    return ("Delayed" if delay else "On time"), delay, gate
