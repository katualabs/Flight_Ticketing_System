"""The read model behind e-tickets, itineraries and emails."""

from __future__ import annotations

from sqlite3 import Row

import segno

from anga.repositories import bookings as bookings_repo
from anga.repositories import passengers as passengers_repo
from anga.repositories import payments as payments_repo
from anga.services import pricing


def qr_data_uri(payload: str) -> str:
    """A QR code as an SVG data URI, which the CSP's ``img-src data:`` permits."""
    return segno.make(payload, error="m").svg_data_uri(scale=4, border=2, dark="#0d1b3e")


def ticket_payload(booking: Row, segment: Row, record: Row) -> str:
    """What a scanner reads: enough to identify the pass, and no ID numbers."""
    return "|".join(
        (
            "ANGA",
            booking["reference"],
            segment["flight_number"],
            segment["departure_date"],
            record["seat_code"] or "LAP",
            record["full_name"],
        )
    )


def booking_detail(booking: Row) -> dict:
    """Everything a page or email needs to show one booking."""
    extras = bookings_repo.extras(booking["id"])
    extras_by_passenger: dict[int, list[Row]] = {}
    for extra in extras:
        extras_by_passenger.setdefault(extra["booking_passenger_id"], []).append(extra)

    segments = []
    for segment in bookings_repo.segments(booking["id"]):
        records = passengers_repo.seat_records_for_segment(segment["segment_id"])
        segments.append(
            {
                "flight": segment,
                "rules": pricing.FARE_RULES[segment["fare_family"]],
                "tickets": [
                    {
                        "record": record,
                        "extras": extras_by_passenger.get(record["booking_passenger_id"], []),
                        "qr": (
                            qr_data_uri(ticket_payload(booking, segment, record))
                            if booking["status"] == "Confirmed"
                            else None
                        ),
                    }
                    for record in records
                ],
            }
        )
    return {
        "booking": booking,
        "segments": segments,
        "passengers": passengers_repo.for_booking(booking["id"]),
        "extras": extras,
        "payments": payments_repo.for_booking(booking["id"]),
        "amount_paid": payments_repo.amount_paid(booking["id"]),
    }
