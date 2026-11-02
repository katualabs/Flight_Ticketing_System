"""Booking rules: quotes, inventory, seats, promos and concurrency."""

from __future__ import annotations

import re
import threading
from datetime import timedelta

import pytest

from anga import clock, db, validators
from anga.repositories import bookings as bookings_repo
from anga.repositories import fares as fares_repo
from anga.repositories import passengers as passengers_repo
from anga.services import booking, pricing
from anga.services.booking import BookingError, SeatTakenError, SoldOutError
from tests.helpers import (
    TODAY,
    free_seat_count,
    future_date,
    get_fare,
    get_flight,
    make_booking,
    make_draft,
)


def free_codes(flight_id, cabin="Economy"):
    return sorted(booking.available_seat_codes(flight_id, cabin))


def test_reference_format(seeded):
    assert re.fullmatch(r"AN[A-HJ-NP-Z2-9]{6}", booking.generate_reference())


def test_booking_takes_inventory_and_seats(seeded):
    fare = get_fare()
    seats_before = free_seat_count(fare["flight_id"])
    made = make_booking(adults=2)
    assert made["status"] == "Pending"
    assert fares_repo.get_by_id(fare["id"])["available_seats"] == fare["available_seats"] - 2
    assert free_seat_count(fare["flight_id"]) == seats_before - 2


def test_infant_takes_no_seat_or_inventory_but_pays(seeded):
    fare = get_fare()
    draft = make_draft(adults=1, infants=1)
    quote = booking.quote_draft(draft)
    adult_only = booking.quote_draft(make_draft(adults=1))
    assert quote.total > adult_only.total
    made = booking.create_booking(draft)
    assert fares_repo.get_by_id(fare["id"])["available_seats"] == fare["available_seats"] - 1
    segment = bookings_repo.segments(made["id"])[0]
    records = passengers_repo.seat_records_for_segment(segment["segment_id"])
    assert sorted(r["seat_id"] is None for r in records) == [False, True]


def test_child_pays_the_child_rate(seeded):
    one = booking.quote_draft(make_draft(adults=1))
    family = booking.quote_draft(make_draft(adults=1, children=1))
    assert family.subtotal == one.subtotal + pricing.round_price(one.subtotal * 0.75)


def test_round_trip_has_two_segments(seeded):
    made = make_booking(return_number="AN102", return_days=10)
    segments = bookings_repo.segments(made["id"])
    assert [s["direction"] for s in segments] == ["outbound", "return"]
    assert made["trip_type"] == "round_trip"
    assert made["subtotal"] == sum(s["fare_paid"] for s in segments)


def test_return_must_depart_after_outbound(seeded):
    with pytest.raises(BookingError, match="after your outbound"):
        make_draft(days=10, return_number="AN102", return_days=7)


def test_selected_seat_is_assigned_and_charged(seeded):
    draft = make_draft()
    flight = get_flight()
    paid = next(
        seat["seat_code"]
        for seat in booking.seats_repo.free_in_cabin(flight["id"], "Economy")
        if seat["price_extra"] == 1500
    )
    draft["seats"] = {"0": {"0": paid}}
    quote = booking.quote_draft(draft)
    assert quote.seats_total == 1500
    made = booking.create_booking(draft)
    assert made["seats_total"] == 1500
    assert made["total"] == made["subtotal"] + 1500


def test_auto_assignment_never_charges(seeded):
    made = make_booking()
    assert made["seats_total"] == 0
    segment = bookings_repo.segments(made["id"])[0]
    record = passengers_repo.seat_records_for_segment(segment["segment_id"])[0]
    assert record["seat_code"]
    assert record["seat_price_paid"] == 0


def test_seat_double_booking_is_prevented(seeded):
    flight = get_flight()
    code = free_codes(flight["id"])[0]
    first = make_draft()
    first["seats"] = {"0": {"0": code}}
    booking.create_booking(first)
    second = make_draft()
    second["seats"] = {"0": {"0": code}}
    with pytest.raises(SeatTakenError):
        booking.create_booking(second)


def test_failed_booking_leaves_nothing_behind(seeded):
    flight = get_flight()
    fare = get_fare()
    code = free_codes(flight["id"])[0]
    first = make_draft()
    first["seats"] = {"0": {"0": code}}
    booking.create_booking(first)
    before = fares_repo.get_by_id(fare["id"])["available_seats"]
    count = db.fetch_value("SELECT COUNT(*) FROM bookings")
    second = make_draft()
    second["seats"] = {"0": {"0": code}}
    with pytest.raises(SeatTakenError):
        booking.create_booking(second)
    assert fares_repo.get_by_id(fare["id"])["available_seats"] == before
    assert db.fetch_value("SELECT COUNT(*) FROM bookings") == count


def test_capacity_exceeded(seeded):
    fare = get_fare()
    draft = make_draft()
    db.execute("UPDATE fares SET available_seats = 0 WHERE id = ?", (fare["id"],))
    with pytest.raises(SoldOutError):
        booking.create_booking(draft)


def test_new_draft_rejects_when_fare_has_too_few_seats(seeded):
    fare = get_fare()
    db.execute("UPDATE fares SET available_seats = 1 WHERE id = ?", (fare["id"],))
    with pytest.raises(SoldOutError):
        booking.new_draft(fare["id"], None, 2, 0, 0)


def test_concurrent_last_seat_race(app):
    """Two real connections race for one remaining seat: exactly one may win."""
    with app.app_context():
        fare = get_fare()
        db.execute(
            "UPDATE fares SET available_seats = 1 WHERE id = ?",
            (fare["id"],),
        )
        draft = make_draft()
        bookings_before = db.fetch_value("SELECT COUNT(*) FROM bookings")

    results: list[str] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        with app.app_context():
            barrier.wait()
            clock.freeze(clock.now())
            try:
                booking.create_booking(draft)
                results.append("booked")
            except SoldOutError:
                results.append("sold out")

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == ["booked", "sold out"]
    with app.app_context():
        assert fares_repo.get_by_id(fare["id"])["available_seats"] == 0
        assert db.fetch_value("SELECT COUNT(*) FROM bookings") == bookings_before + 1


def test_price_change_is_caught_before_charging(seeded):
    draft = make_draft()
    with pytest.raises(booking.PriceChangedError):
        booking.create_booking(draft, expected_total=1)


def test_cancelled_flight_cannot_be_booked(seeded):
    draft = make_draft()
    db.execute("UPDATE flights SET status = 'Cancelled' WHERE id = ?", (get_flight()["id"],))
    with pytest.raises(BookingError, match="cancelled"):
        booking.create_booking(draft)


def test_departed_flight_cannot_be_booked(seeded):
    fare = get_fare("AN101", 0)
    clock.freeze(clock.now() + timedelta(hours=2))
    with pytest.raises(BookingError, match="departed"):
        booking.new_draft(fare["id"], None, 1, 0, 0)


def test_promo_percent_applies_and_counts_a_use(seeded):
    draft = make_draft(family="Flex")
    quote = booking.apply_promo_code(draft, "karibu10")
    assert quote.promo_ok
    assert quote.discount == round(quote.subtotal * 0.1)
    made = booking.create_booking(draft)
    assert made["discount"] == quote.discount
    assert booking.promos_repo.get_by_code("KARIBU10")["used_count"] == 1


def test_promo_min_spend_message(seeded):
    draft = make_draft(family="Lite")
    quote = booking.apply_promo_code(draft, "KARIBU10")
    assert not quote.promo_ok
    assert "minimum spend" in quote.promo_message
    assert draft["promo"] is None


def test_expired_promo_is_rejected(seeded):
    quote = booking.apply_promo_code(make_draft(), "EXPIRED5")
    assert "expired" in quote.promo_message


def test_coastal_promo_rejected_inland(seeded):
    quote = booking.apply_promo_code(make_draft("AN201", family="Flex"), "COAST2026")
    assert "coastal" in quote.promo_message


def test_coastal_promo_accepted_on_coast(seeded):
    assert booking.apply_promo_code(make_draft(), "COAST2026").discount == 1500


def test_promo_cap_cannot_be_overrun(seeded):
    db.execute("UPDATE promo_codes SET max_uses = 1 WHERE code = 'COAST2026'")
    first = make_draft()
    booking.apply_promo_code(first, "COAST2026")
    second = make_draft()
    booking.apply_promo_code(second, "COAST2026")
    booking.create_booking(first)
    with pytest.raises(BookingError):
        booking.create_booking(second)


def test_extras_price_per_passenger_per_segment(seeded):
    draft = make_draft(adults=2, return_number="AN102")
    draft["extras"] = {"0": {"BAG23": 2}, "1": {"PRIORITY": 1}}
    quote = booking.quote_draft(draft)
    assert quote.extras_total == (2500 * 2 + 800) * 2
    made = booking.create_booking(draft)
    assert made["extras_total"] == quote.extras_total
    assert len(bookings_repo.extras(made["id"])) == 2


def test_hold_expiry_releases_seats_inventory_and_promo(seeded):
    fare = get_fare(family="Flex")
    before = fare["available_seats"]
    seats_before = free_seat_count(fare["flight_id"])
    draft = make_draft(family="Flex", adults=2)
    booking.apply_promo_code(draft, "KARIBU10")
    made = booking.create_booking(draft, expires_at=clock.now() + timedelta(hours=24))
    assert booking.expire_holds() == 0
    assert booking.expire_holds(clock.now() + timedelta(hours=25)) >= 1
    after = bookings_repo.get(made["id"])
    assert after["status"] == "Cancelled"
    assert after["cancelled_at"]
    assert fares_repo.get_by_id(fare["id"])["available_seats"] == before
    assert free_seat_count(fare["flight_id"]) == seats_before
    assert booking.promos_repo.get_by_code("KARIBU10")["used_count"] == 0


def test_seat_map_reflects_layout_and_availability(seeded):
    flight = get_flight()
    result = booking.seat_map(flight["id"], flight["aircraft_code"], "Economy")
    numbers = [row.number for row in result["rows"]]
    assert 13 not in numbers
    assert numbers[0] == 10
    exit_row = next(row for row in result["rows"] if row.number == 18)
    assert exit_row.is_exit
    assert exit_row.cells[3] is None
    seat = exit_row.cells[0]
    assert "window" in seat.description
    assert "extra legroom" in seat.description


def test_validate_seats_flags_duplicates_and_taken(seeded):
    draft = make_draft(adults=2)
    code = free_codes(draft["segments"][0]["flight_id"])[0]
    errors = booking.validate_seat_choices(draft, {"0": {"0": code, "1": code}})
    assert "two passengers" in errors["seat_0_1"]
    errors = booking.validate_seat_choices(draft, {"0": {"0": "99Z"}})
    assert "taken" in errors["seat_0_0"]


# ------------------------------------------------------------------ validators


def form_for(**overrides):
    base = {
        "name_0": "Amina Otieno",
        "id_0": "A1234567",
        "email": "amina@example.com",
        "phone": "+254 712 345 678",
    }
    return {**base, **overrides}


def test_valid_passenger_form():
    people, contact, errors = validators.validate_passengers(form_for(), ["adult"], TODAY)
    assert errors == {}
    assert people[0]["full_name"] == "Amina Otieno"
    assert contact["phone"] == "+254712345678"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "not-an-email"),
        ("email", "a@b"),
        ("phone", "12"),
        ("phone", "abc"),
        ("name_0", "Madonna"),
        ("name_0", "R2 D2"),
        ("name_0", "<script> alert"),
        ("id_0", "12"),
        ("id_0", "bad id!"),
    ],
)
def test_invalid_passenger_fields(field, value):
    _, _, errors = validators.validate_passengers(form_for(**{field: value}), ["adult"], TODAY)
    assert field in errors


def test_names_accept_apostrophes_hyphens_and_accents():
    for name in ("Ng'ang'a Kamau", "Anne-Marie Wafula", "José Núñez", "Dr. Achieng Odhiambo"):
        _, _, errors = validators.validate_passengers(form_for(name_0=name), ["adult"], TODAY)
        assert "name_0" not in errors, name


def test_child_and_infant_ages_are_checked():
    types = ["adult", "child", "infant"]
    good = form_for(
        name_1="Child Otieno",
        id_1="C1234567",
        dob_1="2018-01-01",
        name_2="Baby Otieno",
        id_2="B1234567",
        dob_2="2025-06-01",
    )
    assert validators.validate_passengers(good, types, TODAY)[2] == {}
    bad = {**good, "dob_1": "2000-01-01", "dob_2": "2020-01-01"}
    errors = validators.validate_passengers(bad, types, TODAY)[2]
    assert "2 to 11" in errors["dob_1"]
    assert "under 2" in errors["dob_2"]
    assert "dob_1" in validators.validate_passengers({**good, "dob_1": "soon"}, types, TODAY)[2]
    assert (
        "after the flight"
        in validators.validate_passengers({**good, "dob_2": future_date(90)}, types, TODAY)[2][
            "dob_2"
        ]
    )


@pytest.mark.parametrize(
    ("form", "key"),
    [
        ({"adults": "0"}, "adults"),
        ({"adults": "x"}, "adults"),
        ({"adults": "6", "children": "4"}, "adults"),
        ({"adults": "1", "infants": "2"}, "infants"),
    ],
)
def test_party_validation(form, key):
    assert key in validators.validate_party(form)[1]


def test_parse_extras_ignores_unknown_and_infants(seeded):
    draft = make_draft(adults=1, infants=1)
    form = {
        "bag_0": "2",
        "meal_0": "MEAL_VEG",
        "priority_0": "1",
        "lounge_0": "1",
        "bag_1": "3",
        "meal_1": "MEAL_VEG",
    }
    extras = validators.parse_extras(form, draft, booking.extras_catalogue())
    assert extras == {"0": {"BAG23": 2, "MEAL_VEG": 1, "PRIORITY": 1, "LOUNGE": 1}}
    assert (
        validators.parse_extras(
            {"bag_0": "99", "meal_0": "FREE"}, draft, booking.extras_catalogue()
        )
        == {}
    )
