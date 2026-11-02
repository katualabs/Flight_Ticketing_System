"""Booking rules: quoting a draft, and turning it into a booking atomically."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from sqlite3 import Row

from anga import clock
from anga.db import transaction
from anga.repositories import airports as airports_repo
from anga.repositories import bookings as bookings_repo
from anga.repositories import drafts as drafts_repo
from anga.repositories import extras as extras_repo
from anga.repositories import fares as fares_repo
from anga.repositories import flights as flights_repo
from anga.repositories import passengers as passengers_repo
from anga.repositories import promos as promos_repo
from anga.repositories import seats as seats_repo
from anga.services import pricing
from anga.services.search import live_price

REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DRAFT_MAX_AGE_DAYS = 2


class BookingError(Exception):
    """A rule stopped the booking; the message is safe to show the customer."""


class SoldOutError(BookingError):
    pass


class SeatTakenError(BookingError):
    pass


class PriceChangedError(BookingError):
    pass


def generate_reference() -> str:
    """AN + six characters from an alphabet with no lookalikes (0/O, 1/I)."""
    while True:
        reference = "AN" + "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(6))
        if not bookings_repo.reference_exists(reference):
            return reference


# ---------------------------------------------------------------- draft storage


def load_draft(token: str | None) -> dict | None:
    return drafts_repo.load(token) if token else None


def save_draft(token: str, draft: dict) -> None:
    drafts_repo.save(token, draft, clock.timestamp())


def delete_draft(token: str) -> None:
    drafts_repo.delete(token)


def purge_old_drafts() -> None:
    cutoff = clock.now() - timedelta(days=DRAFT_MAX_AGE_DAYS)
    drafts_repo.delete_older_than(cutoff.isoformat(timespec="seconds"))


def new_draft(
    outbound_fare_id: int | None,
    return_fare_id: int | None,
    adults: int,
    children: int,
    infants: int,
) -> dict:
    """Start a draft from the fares chosen on the results page."""
    fare_ids = [("outbound", outbound_fare_id)]
    if return_fare_id:
        fare_ids.append(("return", return_fare_id))
    segments = []
    seats_needed = adults + children
    for direction, fare_id in fare_ids:
        fare = fares_repo.get_by_id(fare_id) if fare_id else None
        if fare is None:
            raise BookingError("Please choose a fare for each flight.")
        flight = flights_repo.get(fare["flight_id"])
        _check_flight_bookable(flight)
        if fare["available_seats"] < seats_needed:
            raise SoldOutError("Sorry, that fare no longer has enough seats.")
        segments.append(
            {
                "flight_id": fare["flight_id"],
                "cabin": fare["cabin"],
                "family": fare["fare_family"],
                "direction": direction,
            }
        )
    if len(segments) == 2 and _departure_of(segments[1]) <= _departure_of(segments[0]):
        raise BookingError("Your return flight must depart after your outbound flight.")
    types = ["adult"] * adults + ["child"] * children + ["infant"] * infants
    return {
        "trip_type": "round_trip" if return_fare_id else "one_way",
        "segments": segments,
        "passenger_types": types,
        "passengers": [],
        "contact": {},
        "seats": {},
        "extras": {},
        "promo": None,
    }


def _departure_of(segment: dict) -> datetime:
    return flight_departure(flights_repo.get(segment["flight_id"]))


def flight_departure(flight: Row) -> datetime:
    """A flight's scheduled departure in network time, whatever its airport's zone."""
    local = datetime.fromisoformat(f"{flight['departure_date']}T{flight['departure_time']}")
    return clock.local_to_network(local, flight["origin_tz"])


def _check_flight_bookable(flight: Row | None) -> None:
    if flight is None:
        raise BookingError("That flight is no longer available.")
    if flight["status"] == "Cancelled":
        raise BookingError(f"Flight {flight['flight_number']} has been cancelled.")
    if flight_departure(flight) <= clock.now():
        raise BookingError(f"Flight {flight['flight_number']} has already departed.")


# ---------------------------------------------------------------------- quoting


@dataclass
class QuoteLine:
    label: str
    amount: int


@dataclass
class Quote:
    fare_lines: list[QuoteLine] = field(default_factory=list)
    seat_lines: list[QuoteLine] = field(default_factory=list)
    extra_lines: list[QuoteLine] = field(default_factory=list)
    segment_fares: list[int] = field(default_factory=list)
    subtotal: int = 0
    seats_total: int = 0
    extras_total: int = 0
    discount: int = 0
    promo_code: str | None = None
    promo_message: str | None = None
    promo_ok: bool = False

    @property
    def total(self) -> int:
        return self.subtotal + self.seats_total + self.extras_total - self.discount


def non_infant_indexes(draft: dict) -> list[int]:
    return [i for i, kind in enumerate(draft["passenger_types"]) if kind != "infant"]


def is_coastal(segments: list[Row]) -> bool:
    return any(seg["origin_coastal"] or seg["destination_coastal"] for seg in segments)


def draft_flights(draft: dict) -> list[Row]:
    return [flights_repo.get(segment["flight_id"]) for segment in draft["segments"]]


def quote_draft(draft: dict, today: date | None = None) -> Quote:
    """Price a draft from current inventory. The server is the only pricing authority."""
    today = today or clock.today()
    quote = Quote()
    flights = draft_flights(draft)
    types = draft["passenger_types"]
    for index, (segment, flight) in enumerate(zip(draft["segments"], flights, strict=True)):
        fare = fares_repo.get(segment["flight_id"], segment["cabin"], segment["family"])
        price = live_price(fare, date.fromisoformat(flight["departure_date"]))
        fare_total = sum(pricing.passenger_fare(price, kind) for kind in types)
        quote.segment_fares.append(fare_total)
        quote.fare_lines.append(
            QuoteLine(
                f"{flight['flight_number']} {flight['origin']}–{flight['destination']}"
                f" · {segment['family']}",
                fare_total,
            )
        )
        quote.seats_total += _quote_seats(quote, draft, index, segment, flight)
    quote.subtotal = sum(quote.segment_fares)
    quote.extras_total = _quote_extras(quote, draft)
    _apply_promo(quote, draft, flights, today)
    return quote


def _quote_seats(quote: Quote, draft: dict, index: int, segment: dict, flight: Row) -> int:
    total = 0
    chosen = draft["seats"].get(str(index), {})
    for seat_code in chosen.values():
        seat = seats_repo.get(segment["flight_id"], seat_code)
        if seat and seat["price_extra"]:
            total += seat["price_extra"]
            quote.seat_lines.append(
                QuoteLine(f"Seat {seat_code} on {flight['flight_number']}", seat["price_extra"])
            )
    return total


def extras_catalogue() -> list[Row]:
    return extras_repo.active()


def _quote_extras(quote: Quote, draft: dict) -> int:
    catalogue = {extra["code"]: extra for extra in extras_catalogue()}
    segments = len(draft["segments"])
    totals: dict[str, tuple[int, int]] = {}
    for choices in draft["extras"].values():
        for code, quantity in choices.items():
            extra = catalogue.get(code)
            if extra is None or quantity <= 0:
                continue
            count, amount = totals.get(code, (0, 0))
            totals[code] = (count + quantity, amount + extra["price"] * quantity * segments)
    for code, (count, amount) in totals.items():
        quote.extra_lines.append(QuoteLine(f"{catalogue[code]['name']} × {count}", amount))
    return sum(amount for _, amount in totals.values())


def _apply_promo(quote: Quote, draft: dict, flights: list[Row], today: date) -> None:
    code = draft.get("promo")
    if not code:
        return
    result = pricing.evaluate_promo(
        promos_repo.get_by_code(code), quote.subtotal, is_coastal(flights), today
    )
    quote.promo_code = code
    quote.promo_message = result.message
    quote.promo_ok = result.ok
    quote.discount = result.discount


def apply_promo_code(draft: dict, code: str) -> Quote:
    """Set a promo on the draft; a rejected code is dropped but its message returned."""
    draft["promo"] = code.strip().upper() or None
    quote = quote_draft(draft)
    if not quote.promo_ok:
        draft["promo"] = None
    return quote


def fare_rules_for(draft: dict) -> list[dict]:
    return [
        {
            "flight": flight,
            "family": segment["family"],
            "rules": pricing.FARE_RULES[segment["family"]],
        }
        for segment, flight in zip(draft["segments"], draft_flights(draft), strict=True)
    ]


# -------------------------------------------------------------------- seat maps


@dataclass
class SeatCell:
    code: str
    available: bool
    is_window: bool
    is_aisle: bool
    extra_legroom: bool
    price: int

    @property
    def description(self) -> str:
        traits = [
            "window" if self.is_window else "",
            "aisle" if self.is_aisle else "",
            "extra legroom" if self.extra_legroom else "",
            f"KSh {self.price:,} extra" if self.price else "",
        ]
        return ", ".join(trait for trait in traits if trait) or "standard"


@dataclass
class SeatRow:
    number: int
    is_exit: bool
    cells: list[SeatCell | None]


def seat_map(flight_id: int, aircraft_code: str, cabin: str) -> dict:
    """Rows for one cabin in layout order; None marks the aisle."""
    layout = json.loads(airports_repo.get_aircraft(aircraft_code)["layout"])
    cabin_layout = next(item for item in layout["cabins"] if item["name"] == cabin)
    seats = {seat["seat_code"]: seat for seat in seats_repo.for_flight(flight_id)}
    rows = []
    exit_rows = set(cabin_layout.get("exit_rows", []))
    for number in range(cabin_layout["first_row"], cabin_layout["last_row"] + 1):
        if number in cabin_layout.get("skip_rows", []):
            continue
        cells: list[SeatCell | None] = []
        for column in cabin_layout["columns"]:
            if column == "|":
                cells.append(None)
                continue
            seat = seats.get(f"{number}{column}")
            if seat is None:
                continue
            cells.append(
                SeatCell(
                    code=seat["seat_code"],
                    available=not seat["blocked"] and seat["booking_passenger_id"] is None,
                    is_window=bool(seat["is_window"]),
                    is_aisle=bool(seat["is_aisle"]),
                    extra_legroom=bool(seat["extra_legroom"]),
                    price=seat["price_extra"],
                )
            )
        rows.append(SeatRow(number, number in exit_rows, cells))
    return {"columns": cabin_layout["columns"], "rows": rows}


def available_seat_codes(flight_id: int, cabin: str) -> set[str]:
    return {seat["seat_code"] for seat in seats_repo.free_in_cabin(flight_id, cabin)}


def validate_seat_choices(draft: dict, chosen: dict[str, dict[str, str]]) -> dict[str, str]:
    """Check picks against live availability; returns errors keyed by form field."""
    errors = {}
    for seg_index, seats in chosen.items():
        segment = draft["segments"][int(seg_index)]
        free = available_seat_codes(segment["flight_id"], segment["cabin"])
        seen = set()
        for pax_index, code in seats.items():
            field_name = f"seat_{seg_index}_{pax_index}"
            if code in seen:
                errors[field_name] = f"Seat {code} is selected for two passengers."
            elif code not in free:
                errors[field_name] = f"Seat {code} has just been taken. Please choose another."
            seen.add(code)
    return errors


# --------------------------------------------------------------- creating a booking


def create_booking(
    draft: dict,
    user_id: int | None = None,
    expires_at: datetime | None = None,
    expected_total: int | None = None,
) -> Row:
    """Turn a draft into a Pending booking, taking seats and inventory atomically.

    Everything happens in one transaction with guarded updates, so a failure at
    any point (sold-out bucket, taken seat, exhausted promo) leaves nothing
    behind, and concurrent requests can never oversell.
    """
    with transaction():
        flights = draft_flights(draft)
        for flight in flights:
            _check_flight_bookable(flight)
        # Priced before inventory moves, matching the load the customer was quoted.
        quote = quote_draft(draft)
        if expected_total is not None and quote.total != expected_total:
            raise PriceChangedError(
                f"The price has changed to KSh {quote.total:,}. Please review and try again."
            )
        promo_id = _claim_promo(draft, quote)
        booking_id = bookings_repo.insert(
            generate_reference(),
            user_id,
            draft["contact"]["email"],
            draft["contact"]["phone"],
            draft["trip_type"],
            quote.subtotal,
            quote.seats_total,
            quote.extras_total,
            quote.discount,
            quote.total,
            promo_id,
            clock.timestamp(),
            expires_at.isoformat(timespec="seconds") if expires_at else None,
        )
        passenger_ids = [
            passengers_repo.insert(
                booking_id,
                passenger["full_name"],
                passenger["id_number"],
                passenger.get("date_of_birth"),
                kind,
            )
            for passenger, kind in zip(draft["passengers"], draft["passenger_types"], strict=True)
        ]
        for index, segment in enumerate(draft["segments"]):
            _take_segment(draft, index, segment, booking_id, passenger_ids, quote)
        _store_extras(draft, booking_id, passenger_ids)
        return bookings_repo.get(booking_id)


def _claim_promo(draft: dict, quote: Quote) -> int | None:
    if not draft.get("promo"):
        return None
    if not quote.promo_ok:
        # Booking at full price would silently charge more than the customer agreed to.
        raise PriceChangedError(quote.promo_message)
    promo = promos_repo.get_by_code(draft["promo"])
    if not promos_repo.claim_use(promo["id"]):
        raise PriceChangedError("That promo code has just reached its usage limit.")
    return promo["id"]


def _take_segment(
    draft: dict,
    index: int,
    segment: dict,
    booking_id: int,
    passenger_ids: list[int],
    quote: Quote,
) -> None:
    fare = fares_repo.get(segment["flight_id"], segment["cabin"], segment["family"])
    seated = non_infant_indexes(draft)
    if not fares_repo.take_inventory(fare["id"], len(seated)):
        raise SoldOutError("Sorry, the last seats on this fare have just been sold.")
    segment_id = bookings_repo.insert_segment(
        booking_id,
        segment["flight_id"],
        segment["cabin"],
        segment["family"],
        segment["direction"],
        quote.segment_fares[index],
    )
    chosen = draft["seats"].get(str(index), {})
    for pax_index, kind in enumerate(draft["passenger_types"]):
        passenger_id = passenger_ids[pax_index]
        if kind == "infant":
            passengers_repo.insert_seat_record(passenger_id, segment_id, None, 0)
            continue
        code = chosen.get(str(pax_index))
        if code:
            seat = claim_named_seat(segment["flight_id"], code, passenger_id)
        else:
            seat = auto_assign_seat(segment["flight_id"], segment["cabin"], passenger_id)
        passengers_repo.insert_seat_record(
            passenger_id, segment_id, seat["id"], seat["price_extra"] if code else 0
        )


def claim_named_seat(flight_id: int, code: str, passenger_id: int) -> Row:
    seat = seats_repo.get(flight_id, code)
    if seat is None or not seats_repo.claim(seat["id"], passenger_id):
        raise SeatTakenError(f"Seat {code} has just been taken. Please choose another.")
    return seat


def auto_assign_seat(flight_id: int, cabin: str, passenger_id: int) -> Row:
    """Give a passenger the first free seat, never charging for one they did not pick."""
    for seat in seats_repo.free_in_cabin(flight_id, cabin):
        if seats_repo.claim(seat["id"], passenger_id):
            return seat
    raise SoldOutError("Sorry, this cabin has just sold out.")


def _store_extras(draft: dict, booking_id: int, passenger_ids: list[int]) -> None:
    catalogue = {extra["code"]: extra for extra in extras_catalogue()}
    segments = len(draft["segments"])
    rows = []
    for pax_index, choices in draft["extras"].items():
        for code, quantity in choices.items():
            if code in catalogue and quantity > 0:
                rows.append(
                    (
                        booking_id,
                        passenger_ids[int(pax_index)],
                        code,
                        quantity,
                        catalogue[code]["price"] * quantity * segments,
                    )
                )
    bookings_repo.insert_extras(rows)


# ------------------------------------------------------------------- releasing


def release_inventory(booking: Row) -> None:
    """Give a booking's seats and fare inventory back. Call inside a transaction."""
    for segment in bookings_repo.segments(booking["id"]):
        records = passengers_repo.seat_records_for_segment(segment["segment_id"])
        seated = [record for record in records if record["seat_id"] is not None]
        for record in seated:
            seats_repo.release(record["seat_id"])
        fares_repo.release_inventory(
            segment["flight_id"], segment["cabin"], segment["fare_family"], len(seated)
        )
    if booking["promo_id"]:
        promos_repo.release_use(booking["promo_id"])


def expire_holds(now: datetime | None = None) -> int:
    """Cancel unpaid bookings past their deadline and free what they held."""
    moment = (now or clock.now()).isoformat(timespec="seconds")
    expired = bookings_repo.expired_holds(moment)
    for booking in expired:
        with transaction():
            if bookings_repo.cancel(booking["id"], moment):
                release_inventory(booking)
    return len(expired)
