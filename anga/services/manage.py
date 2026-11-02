"""Post-booking changes: seats, extras, flight changes and cancellations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from sqlite3 import Row

from anga import clock
from anga.db import transaction
from anga.repositories import bookings as bookings_repo
from anga.repositories import fares as fares_repo
from anga.repositories import flights as flights_repo
from anga.repositories import passengers as passengers_repo
from anga.repositories import payments as payments_repo
from anga.repositories import seats as seats_repo
from anga.services import booking as booking_service
from anga.services import loyalty, notifications, payment, preferences, pricing, tickets
from anga.services.booking import BookingError, flight_departure
from anga.services.search import live_price

LOCKED_STATUSES = ("Departed", "Landed", "Boarding")


def lookup(reference: str, email: str) -> Row | None:
    """Find a booking from reference + email.

    Callers show one generic message for any failure, so a wrong email reveals
    nothing about whether a reference exists.
    """
    booking = booking_service.get_by_reference(reference.strip().upper())
    if booking is None or booking["contact_email"].lower() != email.strip().lower():
        return None
    return booking


def _require_changeable(booking: Row) -> None:
    if booking["status"] == "Cancelled":
        raise BookingError("This booking has been cancelled.")


def _require_flight_open(flight: Row) -> None:
    if flight["status"] in LOCKED_STATUSES or flight_departure(flight) <= clock.now():
        raise BookingError("This flight has already closed for changes.")


def _segment_of(booking: Row, segment_id: int) -> Row:
    for segment in bookings_repo.segments(booking["id"]):
        if segment["segment_id"] == segment_id:
            return segment
    raise BookingError("That flight is not part of this booking.")


def _email_change(booking_id: int, message: str) -> None:
    notifications.booking_changed(tickets.booking_detail(bookings_repo.get(booking_id)), message)


# ------------------------------------------------------------------------ seats


def seat_change_view(booking: Row, segment_id: int) -> dict:
    segment = _segment_of(booking, segment_id)
    records = passengers_repo.seat_records_for_segment(segment_id)
    return {
        "segment": segment,
        "records": [record for record in records if record["seat_id"] is not None],
        "map": booking_service.seat_map(
            segment["flight_id"], segment["aircraft_code"], segment["cabin"]
        ),
    }


def change_seat(booking: Row, segment_id: int, passenger_id: int, new_code: str) -> int:
    """Move a passenger to another seat; returns the amount charged.

    A dearer seat is charged the difference. A cheaper one is not refunded,
    the same rule as every other post-booking change.
    """
    _require_changeable(booking)
    segment = _segment_of(booking, segment_id)
    _require_flight_open(segment)
    record = passengers_repo.seat_record(passenger_id, segment_id)
    if record is None or record["booking_id"] != booking["id"] or record["seat_id"] is None:
        raise BookingError("That passenger has no seat to change on this flight.")
    if record["checked_in_at"]:
        raise BookingError("Seats cannot be changed after check-in.")
    if record["seat_code"] == new_code:
        return 0
    with transaction():
        new_seat = seats_repo.get(segment["flight_id"], new_code)
        if new_seat is None or new_seat["cabin"] != segment["cabin"]:
            raise BookingError("That seat is not available in your cabin.")
        booking_service.claim_named_seat(segment["flight_id"], new_code, passenger_id)
        seats_repo.release(record["seat_id"])
        charge = max(0, new_seat["price_extra"] - record["seat_price_paid"])
        passengers_repo.update_seat_record(
            passenger_id,
            segment_id,
            new_seat["id"],
            max(record["seat_price_paid"], new_seat["price_extra"]),
        )
        if charge:
            bookings_repo.add_charges(booking["id"], seats=charge)
            payment.collect_difference(booking, charge, "ST")
    return charge


# ----------------------------------------------------------------------- extras


def add_extras(booking: Row, passenger_id: int, code: str, quantity: int) -> int:
    """Add an extra after booking; returns the amount charged."""
    _require_changeable(booking)
    catalogue = {extra["code"]: extra for extra in booking_service.extras_catalogue()}
    extra = catalogue.get(code)
    if extra is None or not 1 <= quantity <= 3:
        raise BookingError("Choose a valid extra.")
    passenger = next(
        (p for p in passengers_repo.for_booking(booking["id"]) if p["id"] == passenger_id), None
    )
    if passenger is None or passenger["passenger_type"] == "infant":
        raise BookingError("Choose a passenger with a seat.")
    segments = bookings_repo.segments(booking["id"])
    open_segments = [
        s
        for s in segments
        if s["status"] not in LOCKED_STATUSES and flight_departure(s) > clock.now()
    ]
    if not open_segments:
        raise BookingError("All of the flights on this booking have closed for changes.")
    amount = extra["price"] * quantity * len(open_segments)
    with transaction():
        bookings_repo.insert_extras([(booking["id"], passenger_id, code, quantity, amount)])
        bookings_repo.add_charges(booking["id"], extras_amount=amount)
        payment.collect_difference(booking, amount, "EX")
    return amount


# --------------------------------------------------------------- changing flight


def _passenger_types(booking: Row) -> list[str]:
    return [p["passenger_type"] for p in passengers_repo.for_booking(booking["id"])]


def _change_quote(segment: Row, new_fare_total: int) -> pricing.ChangeQuote:
    """A flight the airline cancelled is always rebooked free, even on Lite."""
    if segment["status"] == "Cancelled":
        return pricing.ChangeQuote(True)
    return pricing.change_quote(segment["fare_family"], segment["fare_paid"], new_fare_total)


@dataclass
class ChangeOption:
    flight: Row
    fare_total: int
    quote: pricing.ChangeQuote


def change_options(booking: Row, segment_id: int, day: date) -> list[ChangeOption]:
    """Same-route flights on ``day`` that can take this party in the same fare."""
    segment = _segment_of(booking, segment_id)
    types = _passenger_types(booking)
    seated = sum(1 for kind in types if kind != "infant")
    options = []
    for flight in flights_repo.find(segment["origin"], segment["destination"], day.isoformat()):
        if flight["id"] == segment["flight_id"] or flight_departure(flight) <= clock.now():
            continue
        fare = fares_repo.get(flight["id"], segment["cabin"], segment["fare_family"])
        if fare is None or fare["available_seats"] < seated:
            continue
        price = live_price(fare, day)
        total = sum(pricing.passenger_fare(price, kind) for kind in types)
        options.append(ChangeOption(flight, total, _change_quote(segment, total)))
    return options


def can_change(segment: Row) -> pricing.ChangeQuote:
    """Whether the fare allows a change at all, before any flight is chosen."""
    return _change_quote(segment, segment["fare_paid"])


def _check_trip_order(booking: Row, segment: Row, new_flight: Row) -> None:
    for other in bookings_repo.segments(booking["id"]):
        if other["segment_id"] == segment["segment_id"]:
            continue
        new_departure = flight_departure(new_flight)
        other_departure = flight_departure(other)
        if segment["direction"] == "outbound" and new_departure >= other_departure:
            raise BookingError("Your outbound flight must leave before your return flight.")
        if segment["direction"] == "return" and new_departure <= other_departure:
            raise BookingError("Your return flight must leave after your outbound flight.")


def change_flight(booking: Row, segment_id: int, new_flight_id: int) -> int:
    """Move a segment to another flight atomically; returns the amount charged."""
    _require_changeable(booking)
    segment = _segment_of(booking, segment_id)
    if segment["status"] != "Cancelled":
        _require_flight_open(segment)
    new_flight = flights_repo.get(new_flight_id)
    if (
        new_flight is None
        or (new_flight["origin"], new_flight["destination"])
        != (segment["origin"], segment["destination"])
        or new_flight["status"] == "Cancelled"
        or flight_departure(new_flight) <= clock.now()
    ):
        raise BookingError("That flight is not available.")
    _check_trip_order(booking, segment, new_flight)
    option = next(
        (
            item
            for item in change_options(
                booking, segment_id, date.fromisoformat(new_flight["departure_date"])
            )
            if item.flight["id"] == new_flight_id
        ),
        None,
    )
    if option is None:
        raise booking_service.SoldOutError("That flight no longer has enough seats.")
    if not option.quote.allowed:
        raise BookingError(option.quote.reason)

    with transaction():
        records = passengers_repo.seat_records_for_segment(segment_id)
        seated = [record for record in records if record["seat_id"] is not None]
        fare = fares_repo.get(new_flight_id, segment["cabin"], segment["fare_family"])
        if not fares_repo.take_inventory(fare["id"], len(seated)):
            raise booking_service.SoldOutError("That flight no longer has enough seats.")
        for record in seated:
            seats_repo.release(record["seat_id"])
            seat = booking_service.auto_assign_seat(
                new_flight_id, segment["cabin"], record["booking_passenger_id"]
            )
            passengers_repo.update_seat_record(
                record["booking_passenger_id"], segment_id, seat["id"], 0
            )
        fares_repo.release_inventory(
            segment["flight_id"], segment["cabin"], segment["fare_family"], len(seated)
        )
        passengers_repo.clear_check_in(segment_id)
        bookings_repo.update_segment_flight(
            segment_id, new_flight_id, segment["fare_paid"] + option.quote.difference
        )
        if option.quote.total:
            bookings_repo.add_charges(booking["id"], changes=option.quote.total)
            payment.collect_difference(booking, option.quote.total, "CH")
        if not _has_cancelled_segment(booking["id"]):
            bookings_repo.clear_rebooking(booking["id"])
        _email_change(
            booking["id"],
            f"You are now on {new_flight['flight_number']} on "
            f"{new_flight['departure_date']} at {new_flight['departure_time']}.",
        )
    return option.quote.total


def _has_cancelled_segment(booking_id: int) -> bool:
    return any(s["status"] == "Cancelled" for s in bookings_repo.segments(booking_id))


# ----------------------------------------------------------------- cancellation


@dataclass
class CancellationQuote:
    allowed: bool
    refund: int
    reason: str


def cancellation_quote(booking: Row, waive_fees: bool = False) -> CancellationQuote:
    """What cancelling would refund right now, shown before the customer commits."""
    if booking["status"] == "Cancelled":
        return CancellationQuote(False, 0, "This booking is already cancelled.")
    segments = bookings_repo.segments(booking["id"])
    live = [s for s in segments if s["status"] != "Cancelled"]
    if any(s["status"] in LOCKED_STATUSES or flight_departure(s) <= clock.now() for s in live):
        return CancellationQuote(False, 0, "This trip has already started.")
    paid = payments_repo.amount_paid(booking["id"])
    # An airline-cancelled flight, or staff waiving fees, refunds everything paid.
    if waive_fees or booking["needs_rebooking"]:
        return CancellationQuote(True, paid, "A full refund of the amount paid.")
    first_departure = min(flight_departure(s) for s in live)
    hours = (first_departure - clock.now()) / timedelta(hours=1)
    quote = pricing.refund_quote(
        [(s["fare_family"], s["fare_paid"]) for s in segments],
        booking["subtotal"],
        booking["discount"],
        booking["seats_total"],
        booking["extras_total"],
        paid,
        hours,
        preferences.cancellation_hours(),
    )
    return CancellationQuote(True, quote.amount, quote.reason)


def cancel(booking: Row, waive_fees: bool = False) -> int:
    """Cancel a booking and return the refund. The row itself is never deleted."""
    quote = cancellation_quote(booking, waive_fees)
    if not quote.allowed:
        raise BookingError(quote.reason)
    with transaction():
        if not bookings_repo.cancel(booking["id"], clock.timestamp()):
            raise BookingError("This booking is already cancelled.")
        booking_service.release_inventory(booking)
        payment.record_refund(booking, quote.refund)
        loyalty.reverse_for_booking(booking)
        notifications.booking_cancelled(
            tickets.booking_detail(bookings_repo.get(booking["id"])), quote.refund
        )
    return quote.refund
