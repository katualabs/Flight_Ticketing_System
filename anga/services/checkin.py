"""Online check-in: the window rules, seat assignment and boarding passes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlite3 import Row

from anga import clock
from anga.db import transaction
from anga.repositories import bookings as bookings_repo
from anga.repositories import passengers as passengers_repo
from anga.services import booking as booking_service
from anga.services import preferences, tickets
from anga.services.booking import BookingError, flight_departure

FRONT_OF_CABIN_LAST_ROW = 20
EARLY_GROUP = 1
FRONT_GROUP = 2
REAR_GROUP = 3


@dataclass(frozen=True)
class CheckinWindow:
    state: str  # 'not_open' | 'open' | 'closed'
    opens_at: datetime
    closes_at: datetime

    @property
    def is_open(self) -> bool:
        return self.state == "open"


def window_for(flight: Row, now: datetime | None = None) -> CheckinWindow:
    """Open from 48 hours until 1 hour before departure, both admin-configurable."""
    now = now or clock.now()
    departure = flight_departure(flight)
    opens_at = departure - timedelta(hours=preferences.checkin_open_hours())
    closes_at = departure - timedelta(hours=preferences.checkin_close_hours())
    if now < opens_at:
        state = "not_open"
    elif now >= closes_at or flight["status"] in ("Cancelled", "Departed", "Landed"):
        state = "closed"
    else:
        state = "open"
    return CheckinWindow(state, opens_at, closes_at)


def boarding_group(cabin: str, has_priority: bool, row: int | None) -> int:
    """Premium cabins, priority customers and lap infants board first, then front to back."""
    if cabin != "Economy" or has_priority or row is None:
        return EARLY_GROUP
    return FRONT_GROUP if row <= FRONT_OF_CABIN_LAST_ROW else REAR_GROUP


def _seat_row(seat_code: str | None) -> int | None:
    digits = "".join(ch for ch in seat_code or "" if ch.isdigit())
    return int(digits) if digits else None


def segment_view(booking: Row, segment_id: int) -> dict:
    segment = next(
        (s for s in bookings_repo.segments(booking["id"]) if s["segment_id"] == segment_id), None
    )
    if segment is None:
        raise BookingError("That flight is not part of this booking.")
    return {
        "segment": segment,
        "window": window_for(segment),
        "records": passengers_repo.seat_records_for_segment(segment_id),
    }


def _priority_passengers(booking: Row) -> set[int]:
    return {
        extra["booking_passenger_id"]
        for extra in bookings_repo.extras(booking["id"])
        if extra["type"] == "priority"
    }


def check_in(booking: Row, segment_id: int, passenger_ids: list[int]) -> int:
    """Check in the chosen passengers, assigning seats where missing.

    Returns how many were newly checked in. Sequence numbers come from inside
    the transaction, so two simultaneous check-ins can never share one.
    """
    if booking["status"] != "Confirmed":
        raise BookingError("Only confirmed, paid bookings can check in.")
    view = segment_view(booking, segment_id)
    segment = view["segment"]
    if not view["window"].is_open:
        raise BookingError("Check-in is not open for this flight.")
    by_passenger = {record["booking_passenger_id"]: record for record in view["records"]}
    if not passenger_ids or any(pid not in by_passenger for pid in passenger_ids):
        raise BookingError("Choose at least one passenger on this booking.")

    priority = _priority_passengers(booking)
    count = 0
    with transaction():
        for passenger_id in passenger_ids:
            record = by_passenger[passenger_id]
            if record["checked_in_at"]:
                continue
            seat_code = record["seat_code"]
            if record["passenger_type"] != "infant" and record["seat_id"] is None:
                seat = booking_service.auto_assign_seat(
                    segment["flight_id"], segment["cabin"], passenger_id
                )
                passengers_repo.update_seat_record(passenger_id, segment_id, seat["id"], 0)
                seat_code = seat["seat_code"]
            passengers_repo.mark_checked_in(
                passenger_id,
                segment_id,
                clock.timestamp(),
                passengers_repo.next_boarding_sequence(segment["flight_id"]),
                boarding_group(segment["cabin"], passenger_id in priority, _seat_row(seat_code)),
            )
            count += 1
    return count


def boarding_passes(booking: Row, segment_id: int) -> dict:
    """Passes for everyone checked in on a segment, each with its own QR code."""
    view = segment_view(booking, segment_id)
    segment = view["segment"]
    passes = []
    for record in passengers_repo.seat_records_for_segment(segment_id):
        if not record["checked_in_at"]:
            continue
        payload = (
            f"{tickets.ticket_payload(booking, segment, record)}"
            f"|SEQ{record['boarding_sequence']:03d}|G{record['boarding_group']}"
        )
        passes.append({"record": record, "qr": tickets.qr_data_uri(payload)})
    return {"segment": segment, "passes": passes}
