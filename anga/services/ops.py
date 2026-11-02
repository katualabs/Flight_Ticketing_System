"""Operations rules behind the admin console. Every change writes an audit entry."""

from __future__ import annotations

import csv
import io
from datetime import date
from sqlite3 import IntegrityError, Row

from anga.db import transaction
from anga.repositories import airports as airports_repo
from anga.repositories import bookings as bookings_repo
from anga.repositories import fares as fares_repo
from anga.repositories import flights as flights_repo
from anga.repositories import messages as messages_repo
from anga.repositories import outbox as outbox_repo
from anga.repositories import passengers as passengers_repo
from anga.repositories import promos as promos_repo
from anga.repositories import seats as seats_repo
from anga.repositories import settings as settings_repo
from anga.repositories import users as users_repo
from anga.services import audit, manage, notifications, payment, schedule, tickets

PAGE_SIZE = 25
EDITABLE_SETTINGS = ("usd_rate", "cancellation_hours", "checkin_open_hours", "checkin_close_hours")
# Spreadsheets run cells beginning with these as formulas, so they are neutralised on export.
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class OpsError(Exception):
    """The message is safe to show staff."""


def _csv_safe(value: object) -> object:
    if isinstance(value, str) and value.startswith(CSV_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def to_csv(header: list[str], rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows([[_csv_safe(cell) for cell in row] for row in rows])
    return buffer.getvalue()


def pages_for(total: int) -> int:
    return max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)


def page_offset(page: int) -> int:
    return (max(page, 1) - 1) * PAGE_SIZE


# ---------------------------------------------------------------------- flights


def search_flights(
    query: str | None, origin: str | None, day: str | None, status: str | None, page: int
) -> tuple[list[Row], int]:
    return flights_repo.search_admin(query, origin, day, status, PAGE_SIZE, page_offset(page))


def airports() -> list[Row]:
    return airports_repo.all_airports()


def aircraft() -> list[Row]:
    return airports_repo.all_aircraft()


def route_templates() -> list[Row]:
    return flights_repo.route_templates()


def get_flight(flight_id: int) -> Row | None:
    return flights_repo.get(flight_id)


def fares_for(flight_id: int) -> list[Row]:
    return fares_repo.for_flight(flight_id)


def create_flight(actor_id: int, data: dict) -> int:
    origin = airports_repo.get(data["origin"])
    destination = airports_repo.get(data["destination"])
    if origin is None or destination is None:
        raise OpsError("Choose valid airports.")
    if airports_repo.get_aircraft(data["aircraft_code"]) is None:
        raise OpsError("Choose a valid aircraft.")
    with transaction():
        flight_id = schedule.create_flight(
            data["flight_number"],
            data["departure_date"],
            data["origin"],
            data["destination"],
            data["departure_time"],
            data["duration_minutes"],
            data["aircraft_code"],
            data["base_fare"],
            origin["timezone"],
            destination["timezone"],
        )
        if flight_id is None:
            raise OpsError(f"{data['flight_number']} already flies on that date.")
        audit.record(actor_id, "flight.create", "flight", flight_id, number=data["flight_number"])
    return flight_id


def update_flight_times(actor_id: int, flight: Row, departure_time: str, duration: int) -> None:
    arrival = schedule.arrival_time(
        departure_time, duration, flight["origin_tz"], flight["destination_tz"]
    )
    with transaction():
        flights_repo.update_times(flight["id"], departure_time, arrival, duration)
        audit.record(
            actor_id, "flight.update", "flight", flight["id"], departure=departure_time,
            duration=duration,
        )  # fmt: skip


def delete_flight(actor_id: int, flight: Row) -> None:
    """Only a flight nobody ever booked may be deleted; others must be cancelled."""
    if bookings_repo.count_for_flight(flight["id"]):
        raise OpsError("This flight has bookings. Cancel it instead, so passengers are told.")
    with transaction():
        flights_repo.delete(flight["id"])
        audit.record(
            actor_id, "flight.delete", "flight", flight["id"], number=flight["flight_number"]
        )


def cancel_flight(actor_id: int, flight: Row) -> int:
    """Cancel a flight, marking its bookings for rebooking and telling each passenger."""
    if flight["status"] in ("Departed", "Landed"):
        raise OpsError("A flight that has already departed cannot be cancelled.")
    affected = bookings_repo.active_for_flight(flight["id"])
    with transaction():
        flights_repo.update_status(flight["id"], "Cancelled", 0, flight["gate"])
        for booking in affected:
            bookings_repo.mark_for_rebooking(booking["id"])
            notifications.flight_cancelled(booking, flight)
        audit.record(
            actor_id,
            "flight.cancel",
            "flight",
            flight["id"],
            number=flight["flight_number"],
            bookings=len(affected),
        )
    return len(affected)


def update_status(
    actor_id: int, flight: Row, status: str, delay_minutes: int, gate: str | None
) -> None:
    with transaction():
        flights_repo.update_status(flight["id"], status, delay_minutes, gate)
        audit.record(
            actor_id,
            "flight.status",
            "flight",
            flight["id"],
            number=flight["flight_number"],
            status=status,
            delay=delay_minutes,
            gate=gate,
        )


def update_fare(actor_id: int, fare: Row, price: int, total_seats: int, available: int) -> None:
    """Edit a fare bucket. Capacity cannot drop below what has already been sold."""
    sold = fare["total_seats"] - fare["available_seats"]
    if total_seats < sold:
        raise OpsError(f"{sold} seats are already sold in this fare.")
    if available > total_seats:
        raise OpsError("Available seats cannot exceed the total.")
    if available > total_seats - sold:
        raise OpsError("Available seats cannot include seats that are already sold.")
    # The cabin's buckets must still add up to no more than the seats that exist.
    others = sum(
        other["total_seats"]
        for other in fares_repo.for_flight(fare["flight_id"])
        if other["cabin"] == fare["cabin"] and other["id"] != fare["id"]
    )
    capacity = sum(
        1 for seat in seats_repo.for_flight(fare["flight_id"]) if seat["cabin"] == fare["cabin"]
    )
    if others + total_seats > capacity:
        raise OpsError(f"This cabin only has {capacity} physical seats.")
    with transaction():
        fares_repo.update(fare["id"], price, total_seats, available)
        audit.record(
            actor_id,
            "fare.update",
            "fare",
            fare["id"],
            flight=fare["flight_id"],
            cabin=fare["cabin"],
            family=fare["fare_family"],
            price=price,
        )


def get_fare(fare_id: int) -> Row | None:
    return fares_repo.get_by_id(fare_id)


def bulk_generate(
    actor_id: int, flight_number: str, start: date, end: date, weekdays: str
) -> tuple[int, int]:
    if flights_repo.get_route_template(flight_number) is None:
        raise OpsError("Choose a route from the schedule.")
    with transaction():
        created, skipped = schedule.bulk_generate(flight_number, start, end, weekdays)
        audit.record(
            actor_id,
            "flight.bulk_generate",
            "route",
            flight_number,
            start=start,
            end=end,
            weekdays=weekdays,
            created=created,
        )
    return created, skipped


# --------------------------------------------------------------------- manifest


def manifest(flight_id: int) -> list[Row]:
    return passengers_repo.manifest(flight_id)


def manifest_csv(flight: Row) -> str:
    rows = [
        [
            row["seat_code"] or "LAP",
            row["full_name"],
            row["passenger_type"],
            row["reference"],
            row["cabin"],
            row["fare_family"],
            row["booking_status"],
            "yes" if row["checked_in_at"] else "no",
            row["boarding_sequence"] or "",
            row["extras"] or "",
        ]
        for row in manifest(flight["id"])
    ]
    header = [
        "seat", "name", "type", "reference", "cabin", "fare", "booking_status", "checked_in",
        "sequence", "extras",
    ]  # fmt: skip
    return to_csv(header, rows)


# --------------------------------------------------------------------- bookings


def search_bookings(
    query: str | None, status: str | None, flight_number: str | None, day: str | None, page: int
) -> tuple[list[Row], int]:
    return bookings_repo.search_admin(
        query, status, flight_number, day, PAGE_SIZE, page_offset(page)
    )


def bookings_csv(
    query: str | None, status: str | None, flight_number: str | None, day: str | None
) -> str:
    rows, _ = bookings_repo.search_admin(query, status, flight_number, day, 100_000, 0)
    return to_csv(
        ["reference", "status", "email", "flights", "passengers", "total", "created_at"],
        [
            [
                row["reference"],
                row["status"],
                row["contact_email"],
                row["flights"],
                row["passengers"],
                row["total"],
                row["created_at"],
            ]
            for row in rows
        ],
    )


def booking_detail(reference: str) -> dict | None:
    booking = bookings_repo.get_by_reference(reference)
    return tickets.booking_detail(booking) if booking else None


def confirm_payment(actor_id: int, booking: Row) -> None:
    with transaction():
        payment.mark_paid_by_staff(booking)
        audit.record(actor_id, "booking.confirm_payment", "booking", booking["reference"])


def cancel_booking(actor_id: int, booking: Row, waive_fees: bool) -> int:
    with transaction():
        refund = manage.cancel(booking, waive_fees=waive_fees)
        audit.record(
            actor_id,
            "booking.cancel",
            "booking",
            booking["reference"],
            refund=refund,
            waived=waive_fees,
        )
    return refund


def resend_confirmation(actor_id: int, booking: Row) -> None:
    if booking["status"] != "Confirmed":
        raise OpsError("Only confirmed bookings have an e-ticket to resend.")
    with transaction():
        notifications.booking_confirmation(tickets.booking_detail(booking))
        audit.record(actor_id, "booking.resend", "booking", booking["reference"])


# ----------------------------------------------------------------------- promos


def promos() -> list[Row]:
    return promos_repo.all_promos()


def get_promo(promo_id: int) -> Row | None:
    return promos_repo.get(promo_id)


def save_promo(actor_id: int, data: dict, promo_id: int | None = None) -> None:
    fields = (
        data["code"], data["kind"], data["value"], data["scope"], data["min_spend"],
        data["valid_from"], data["valid_to"], data["max_uses"], data["active"],
    )  # fmt: skip
    try:
        with transaction():
            if promo_id is None:
                promo_id = promos_repo.insert(*fields)
                action = "promo.create"
            else:
                promos_repo.update(promo_id, *fields)
                action = "promo.update"
            audit.record(actor_id, action, "promo", promo_id, code=data["code"])
    except IntegrityError as error:
        raise OpsError("A promo with that code already exists.") from error


def delete_promo(actor_id: int, promo: Row) -> None:
    if promos_repo.count_bookings(promo["id"]):
        raise OpsError("This code has been used. Deactivate it instead of deleting it.")
    with transaction():
        promos_repo.delete(promo["id"])
        audit.record(actor_id, "promo.delete", "promo", promo["id"], code=promo["code"])


# ------------------------------------------------------------------------ users


def users(query: str | None, page: int) -> tuple[list[Row], int]:
    return users_repo.list_all(query, PAGE_SIZE, page_offset(page))


def get_user(user_id: int) -> Row | None:
    return users_repo.get(user_id)


def change_role(actor_id: int, user: Row, role: str) -> None:
    if user["id"] == actor_id:
        raise OpsError("You cannot change your own role.")
    with transaction():
        users_repo.update_role(user["id"], role)
        audit.record(actor_id, "user.role", "user", user["id"], email=user["email"], role=role)


def set_user_disabled(actor_id: int, user: Row, disabled: bool) -> None:
    if user["id"] == actor_id:
        raise OpsError("You cannot disable your own account.")
    with transaction():
        users_repo.set_disabled(user["id"], disabled)
        audit.record(
            actor_id,
            "user.disable" if disabled else "user.enable",
            "user",
            user["id"],
            email=user["email"],
        )


# ------------------------------------------------------------- messages & outbox


def inbox(page: int) -> tuple[list[Row], int]:
    return messages_repo.inbox(PAGE_SIZE, page_offset(page))


def get_message(message_id: int) -> Row | None:
    return messages_repo.get(message_id)


def set_message_read(actor_id: int, message: Row, is_read: bool) -> None:
    messages_repo.set_read(message["id"], is_read)
    audit.record(
        actor_id, "message.read" if is_read else "message.unread", "message", message["id"]
    )


def save_reply_note(actor_id: int, message: Row, note: str) -> None:
    with transaction():
        messages_repo.save_reply_note(message["id"], note)
        audit.record(actor_id, "message.reply_note", "message", message["id"])


def outbox(page: int) -> tuple[list[Row], int]:
    return outbox_repo.recent(PAGE_SIZE, page_offset(page))


def get_email(email_id: int) -> Row | None:
    return outbox_repo.get(email_id)


# --------------------------------------------------------------------- settings


def settings() -> dict[str, str]:
    return settings_repo.all_settings()


def save_settings(actor_id: int, values: dict[str, str]) -> None:
    with transaction():
        for key in EDITABLE_SETTINGS:
            settings_repo.put(key, values[key])
        audit.record(actor_id, "settings.update", "settings", None, **values)
