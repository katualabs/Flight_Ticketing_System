"""Managing a booking after it is made."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from anga import clock, db
from anga.repositories import bookings as bookings_repo
from anga.repositories import fares as fares_repo
from anga.repositories import outbox as outbox_repo
from anga.repositories import passengers as passengers_repo
from anga.repositories import payments as payments_repo
from anga.services import booking, calendar_ics, manage, payment
from anga.services.booking import BookingError
from tests.helpers import free_seat_count, get_fare, get_flight, make_booking, make_draft

EMAIL = "traveller@example.com"


def paid_booking(**overrides):
    made = make_booking(**overrides)
    payment.pay_by_card(made, "4242")
    return bookings_repo.get(made["id"])


def login_booking(client, reference, email="wanjiru@anga.example"):
    return client.post("/manage/", data={"reference": reference, "email": email})


# ---------------------------------------------------------------------- lookup


def test_valid_lookup_redirects_to_itinerary(client):
    response = login_booking(client, "ANDEMO01")
    assert response.status_code == 302
    page = client.get(response.headers["Location"])
    assert b"ANDEMO01" in page.data
    assert b"AN101" in page.data


def test_lookup_is_case_insensitive(client):
    assert login_booking(client, "andemo01", "WANJIRU@anga.example").status_code == 302


@pytest.mark.parametrize(
    ("reference", "email"),
    [("ANDEMO01", "wrong@example.com"), ("ANXXXXXX", "wanjiru@anga.example"), ("", "")],
)
def test_failed_lookups_all_look_the_same(client, reference, email):
    page = login_booking(client, reference, email)
    assert page.status_code == 404
    assert b"We could not find a booking" in page.data
    assert b"Wanjiru" not in page.data
    assert b"AN101" not in page.data


def test_itinerary_is_private_without_verification(client):
    assert client.get("/manage/ANDEMO01").status_code == 404
    for path in ("cancel", "extras", "calendar.ics"):
        assert client.get(f"/manage/ANDEMO01/{path}").status_code == 404
    assert client.post("/manage/ANDEMO01/cancel").status_code == 404


def test_id_numbers_are_masked_on_the_itinerary(client):
    login_booking(client, "ANDEMO01")
    page = client.get("/manage/ANDEMO01")
    assert b"KE29384756" not in page.data
    assert "•".encode() in page.data


# ------------------------------------------------------------------ change seat


def first_record(made):
    segment = bookings_repo.segments(made["id"])[0]
    return segment, passengers_repo.seat_records_for_segment(segment["segment_id"])[0]


def test_change_seat_moves_passenger_and_frees_old_seat(seeded):
    made = paid_booking()
    segment, record = first_record(made)
    free = booking.seats_repo.free_in_cabin(segment["flight_id"], "Economy")
    target = next(seat for seat in free if seat["price_extra"] == 0)
    assert (
        manage.change_seat(
            made, segment["segment_id"], record["booking_passenger_id"], target["seat_code"]
        )
        == 0
    )
    assert booking.seats_repo.get_by_id(record["seat_id"])["booking_passenger_id"] is None
    assert (
        booking.seats_repo.get_by_id(target["id"])["booking_passenger_id"]
        == record["booking_passenger_id"]
    )


def test_dearer_seat_charges_the_difference(seeded):
    made = paid_booking()
    segment, record = first_record(made)
    free = booking.seats_repo.free_in_cabin(segment["flight_id"], "Economy")
    target = next(seat for seat in free if seat["price_extra"] == 1500)
    charged = manage.change_seat(
        made, segment["segment_id"], record["booking_passenger_id"], target["seat_code"]
    )
    assert charged == 1500
    after = bookings_repo.get(made["id"])
    assert after["total"] == made["total"] + 1500
    assert payments_repo.amount_paid(made["id"]) == after["total"]


def test_cannot_take_a_seat_already_taken(seeded):
    first = paid_booking()
    second = paid_booking()
    _, taken = first_record(first)
    segment, record = first_record(second)
    with pytest.raises(BookingError):
        manage.change_seat(
            second, segment["segment_id"], record["booking_passenger_id"], taken["seat_code"]
        )


def test_cannot_change_another_bookings_passenger(seeded):
    first = paid_booking()
    second = paid_booking()
    segment, _ = first_record(first)
    _, other = first_record(second)
    free = booking.seats_repo.free_in_cabin(segment["flight_id"], "Economy")[0]["seat_code"]
    with pytest.raises(BookingError):
        manage.change_seat(first, segment["segment_id"], other["booking_passenger_id"], free)


def test_seat_change_page_and_post(client, app):
    login_booking(client, "ANDEMO01")
    with app.app_context():
        made = booking.get_by_reference("ANDEMO01")
        segment, record = first_record(made)
        free = booking.seats_repo.free_in_cabin(segment["flight_id"], "Economy")[0]["seat_code"]
    url = f"/manage/ANDEMO01/seats/{segment['segment_id']}"
    assert b"data-seat=" in client.get(url).data
    response = client.post(url, data={f"seat_{record['booking_passenger_id']}": free})
    assert response.status_code == 302
    with app.app_context():
        assert (
            passengers_repo.seat_record(record["booking_passenger_id"], segment["segment_id"])[
                "seat_code"
            ]
            == free
        )


def test_seat_page_for_foreign_segment_is_404(client):
    login_booking(client, "ANDEMO01")
    assert client.get("/manage/ANDEMO01/seats/999999").status_code == 404


# ----------------------------------------------------------------------- extras


def test_add_extra_charges_per_open_segment(seeded):
    made = paid_booking(return_number="AN102")
    passenger = passengers_repo.for_booking(made["id"])[0]
    assert manage.add_extras(made, passenger["id"], "BAG23", 1) == 5000
    after = bookings_repo.get(made["id"])
    assert after["extras_total"] == 5000
    assert payments_repo.amount_paid(made["id"]) == after["total"]


@pytest.mark.parametrize(("code", "quantity"), [("NOPE", 1), ("BAG23", 0), ("BAG23", 9)])
def test_add_extra_validation(seeded, code, quantity):
    made = paid_booking()
    passenger = passengers_repo.for_booking(made["id"])[0]
    with pytest.raises(BookingError):
        manage.add_extras(made, passenger["id"], code, quantity)


def test_add_extra_rejects_infants_and_outsiders(seeded):
    made = paid_booking(adults=1, infants=1)
    infant = passengers_repo.for_booking(made["id"])[1]
    with pytest.raises(BookingError):
        manage.add_extras(made, infant["id"], "BAG23", 1)
    with pytest.raises(BookingError):
        manage.add_extras(made, 999999, "BAG23", 1)


def test_extras_page_flow(client):
    login_booking(client, "ANDEMO01")
    page = client.get("/manage/ANDEMO01/extras")
    assert b"Lounge access" in page.data
    response = client.post(
        "/manage/ANDEMO01/extras", data={"passenger_id": "0", "code": "LOUNGE", "quantity": "1"}
    )
    assert response.status_code == 302


# ---------------------------------------------------------------- change flight


def change_target(days=8, number="AN103"):
    return get_flight(number, days)


def test_lite_cannot_change_date(seeded):
    made = paid_booking(family="Lite")
    segment, _ = first_record(made)
    with pytest.raises(BookingError, match="Lite"):
        manage.change_flight(made, segment["segment_id"], change_target()["id"])


def test_classic_change_pays_fee_and_difference(seeded):
    made = paid_booking(family="Classic")
    segment, _ = first_record(made)
    target = change_target()
    option = next(
        o
        for o in manage.change_options(
            made, segment["segment_id"], date.fromisoformat(target["departure_date"])
        )
        if o.flight["id"] == target["id"]
    )
    assert option.quote.fee == 3000
    charged = manage.change_flight(made, segment["segment_id"], target["id"])
    assert charged == option.quote.total
    after = bookings_repo.get(made["id"])
    assert after["total"] == made["total"] + charged
    assert after["changes_total"] == charged
    assert payments_repo.amount_paid(made["id"]) == after["total"]


def test_flex_change_is_free_and_moves_inventory(seeded):
    made = paid_booking(family="Flex")
    segment, record = first_record(made)
    old_fare = fares_repo.get(segment["flight_id"], "Economy", "Flex")
    target = change_target()
    new_before = fares_repo.get(target["id"], "Economy", "Flex")["available_seats"]
    old_free = free_seat_count(segment["flight_id"])
    assert manage.change_flight(made, segment["segment_id"], target["id"]) == 0
    assert bookings_repo.get(made["id"])["total"] == made["total"]
    assert (
        fares_repo.get_by_id(old_fare["id"])["available_seats"] == old_fare["available_seats"] + 1
    )
    assert fares_repo.get(target["id"], "Economy", "Flex")["available_seats"] == new_before - 1
    assert free_seat_count(segment["flight_id"]) == old_free + 1
    moved = passengers_repo.seat_record(record["booking_passenger_id"], segment["segment_id"])
    assert booking.seats_repo.get_by_id(moved["seat_id"])["flight_id"] == target["id"]


def test_change_must_stay_on_the_same_route(seeded):
    made = paid_booking(family="Flex")
    segment, _ = first_record(made)
    with pytest.raises(BookingError):
        manage.change_flight(made, segment["segment_id"], get_flight("AN301", 8)["id"])


def test_outbound_cannot_move_past_the_return(seeded):
    made = paid_booking(family="Flex", return_number="AN102", return_days=8)
    segment, _ = first_record(made)
    with pytest.raises(BookingError, match="before your return"):
        manage.change_flight(made, segment["segment_id"], get_flight("AN103", 12)["id"])


def test_change_flight_when_new_flight_is_full(seeded):
    made = paid_booking(family="Flex")
    segment, _ = first_record(made)
    target = change_target()
    db.execute(
        "UPDATE fares SET available_seats = 0 WHERE flight_id = ? AND fare_family = 'Flex'",
        (target["id"],),
    )
    with pytest.raises(BookingError):
        manage.change_flight(made, segment["segment_id"], target["id"])


def test_change_page_lists_flights_and_lite_is_refused(client, app):
    with app.app_context():
        made = paid_booking(family="Classic")
        lite = paid_booking(family="Lite")
        seg = first_record(made)[0]["segment_id"]
        lite_seg = first_record(lite)[0]["segment_id"]
    client.post("/manage/", data={"reference": made["reference"], "email": EMAIL})
    client.post("/manage/", data={"reference": lite["reference"], "email": EMAIL})
    page = client.get(f"/manage/{made['reference']}/change/{seg}?date=2026-03-10")
    assert b"AN101" in page.data
    assert b"Choose this flight" in page.data
    refused = client.get(f"/manage/{lite['reference']}/change/{lite_seg}")
    assert b"cannot be changed" in refused.data
    assert client.get(f"/manage/{made['reference']}/change/999999").status_code == 404


def test_change_post_via_http(client, app):
    with app.app_context():
        made = paid_booking(family="Flex")
        seg = first_record(made)[0]["segment_id"]
        target = change_target()["id"]
    client.post("/manage/", data={"reference": made["reference"], "email": EMAIL})
    page = client.post(
        f"/manage/{made['reference']}/change/{seg}",
        data={"flight_id": target},
        follow_redirects=True,
    )
    assert b"has been changed" in page.data


def test_passenger_cannot_change_a_departed_flight(seeded):
    made = paid_booking(family="Flex", days=1)
    segment, _ = first_record(made)
    clock.freeze(clock.now() + timedelta(days=2))
    with pytest.raises(BookingError):
        manage.change_flight(made, segment["segment_id"], change_target()["id"])


# ----------------------------------------------------------------- cancellation


def test_cancel_flex_refunds_in_full_and_never_deletes(seeded):
    made = paid_booking(family="Flex")
    fare = get_fare(family="Flex")
    refund = manage.cancel(made)
    assert refund == made["total"]
    after = bookings_repo.get(made["id"])
    assert after is not None
    assert after["status"] == "Cancelled"
    assert after["cancelled_at"]
    assert payments_repo.amount_paid(made["id"]) == 0
    assert fares_repo.get_by_id(fare["id"])["available_seats"] == fare["available_seats"] + 1
    assert passengers_repo.for_booking(made["id"])


def test_cancel_classic_refunds_half(seeded):
    made = paid_booking(family="Classic")
    assert manage.cancel(made) == round(made["subtotal"] * 0.5)


def test_cancel_lite_refunds_nothing_but_releases_seats(seeded):
    made = paid_booking(family="Lite")
    segment = bookings_repo.segments(made["id"])[0]
    free = free_seat_count(segment["flight_id"])
    assert manage.cancel(made) == 0
    assert free_seat_count(segment["flight_id"]) == free + 1


def test_cancel_inside_the_window_refunds_nothing(seeded):
    made = paid_booking(family="Flex", days=1)
    clock.freeze(clock.now().replace(day=3, hour=6))
    assert manage.cancellation_quote(made).refund == 0


def test_cancel_writes_refund_row_and_email(seeded):
    made = paid_booking(family="Flex")
    manage.cancel(made)
    rows = payments_repo.for_booking(made["id"])
    assert [row["kind"] for row in rows] == ["charge", "refund"]
    assert "cancelled" in outbox_repo.for_recipient(EMAIL)[0]["subject"].lower()


def test_cannot_cancel_twice_or_after_departure(seeded):
    made = paid_booking()
    manage.cancel(made)
    with pytest.raises(BookingError):
        manage.cancel(bookings_repo.get(made["id"]))
    other = paid_booking(days=1)
    clock.freeze(clock.now() + timedelta(days=2))
    with pytest.raises(BookingError):
        manage.cancel(other)


def test_cancelled_booking_rejects_further_changes(seeded):
    made = paid_booking()
    segment, record = first_record(made)
    manage.cancel(made)
    gone = bookings_repo.get(made["id"])
    with pytest.raises(BookingError):
        manage.change_seat(gone, segment["segment_id"], record["booking_passenger_id"], "20A")
    with pytest.raises(BookingError):
        manage.add_extras(gone, record["booking_passenger_id"], "BAG23", 1)


def test_cancel_of_unpaid_hold_refunds_nothing(seeded):
    made = make_booking()
    assert manage.cancel(made) == 0
    assert bookings_repo.get(made["id"])["status"] == "Cancelled"


def test_staff_can_waive_fees(seeded):
    made = paid_booking(family="Lite")
    assert manage.cancel(made, waive_fees=True) == made["total"]


def test_cancel_reverses_miles(seeded):
    user_id = db.fetch_value("SELECT id FROM users WHERE email = 'wanjiru@anga.example'")
    before = db.fetch_value("SELECT miles_balance FROM users WHERE id = ?", (user_id,))
    draft = make_draft(family="Flex")
    made = booking.create_booking(draft, user_id=user_id)
    payment.pay_by_card(made, "4242")
    earned = db.fetch_value("SELECT miles_balance FROM users WHERE id = ?", (user_id,))
    assert earned > before
    manage.cancel(bookings_repo.get(made["id"]))
    assert db.fetch_value("SELECT miles_balance FROM users WHERE id = ?", (user_id,)) == before


def test_cancel_pages(client):
    login_booking(client, "ANDEMO01")
    page = client.get("/manage/ANDEMO01/cancel")
    assert b"Refund due" in page.data
    done = client.post("/manage/ANDEMO01/cancel", follow_redirects=True)
    assert b"Booking cancelled" in done.data
    again = client.get("/manage/ANDEMO01/cancel")
    assert b"already cancelled" in again.data


# ------------------------------------------------------------------ calendar file


def test_calendar_download(client):
    login_booking(client, "ANDEMO01")
    response = client.get("/manage/ANDEMO01/calendar.ics")
    assert response.mimetype == "text/calendar"
    assert 'filename="ANDEMO01.ics"' in response.headers["Content-Disposition"]
    body = response.get_data(as_text=True)
    assert body.count("BEGIN:VEVENT") == 2
    assert "SUMMARY:AN101 Nairobi to Mombasa" in body
    # Tomorrow 08:00 in Nairobi is 05:00 UTC, and the stamp is 10:00 EAT = 07:00 UTC.
    assert "DTSTART:20260303T050000Z" in body
    assert "DTSTAMP:20260302T070000Z" in body


def test_ics_uses_utc_escaping_and_crlf():
    flight = calendar_ics.CalendarFlight(
        "AN1", "NBO", "Nai;robi", "MBA", "Mombasa, Kenya", clock.now(), 60
    )
    text = calendar_ics.build_ics("ANTEST22", [flight], clock.now())
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.endswith("END:VCALENDAR\r\n")
    assert "Nai\\;robi" in text
    assert "Mombasa\\, Kenya" in text
    assert "DTSTART:20260302T100000Z" in text
    assert "DTEND:20260302T110000Z" in text


def test_ics_folds_long_lines():
    flight = calendar_ics.CalendarFlight("AN1", "NBO", "N" * 200, "MBA", "Mombasa", clock.now(), 60)
    text = calendar_ics.build_ics("ANTEST22", [flight], clock.now())
    assert all(len(line) <= 75 for line in text.split("\r\n"))
