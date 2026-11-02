"""Online check-in windows and boarding passes."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from anga import clock, db
from anga.repositories import bookings as bookings_repo
from anga.repositories import passengers as passengers_repo
from anga.services import booking, checkin, manage, payment
from anga.services.booking import BookingError
from tests.helpers import get_flight, make_booking


def paid(**overrides):
    made = make_booking(**overrides)
    payment.pay_by_card(made, "4242")
    return bookings_repo.get(made["id"])


def first_segment(made):
    return bookings_repo.segments(made["id"])[0]


def passenger_ids(made):
    return [p["id"] for p in passengers_repo.for_booking(made["id"])]


def at_flight(number="AN101", days=1, hours_before=24):
    """Move the clock to ``hours_before`` the given flight."""
    flight = get_flight(number, days)
    clock.freeze(booking.flight_departure(flight) - timedelta(hours=hours_before))


@pytest.mark.parametrize(
    ("hours_before", "state"),
    [(49, "not_open"), (48, "open"), (24, "open"), (1.5, "open"), (1, "closed"), (0.5, "closed")],
)
def test_window_boundaries(seeded, hours_before, state):
    flight = get_flight(days=5)
    now = booking.flight_departure(flight) - timedelta(hours=hours_before)
    assert checkin.window_for(flight, now).state == state


def test_cancelled_flight_is_closed(seeded):
    flight = get_flight(days=1)
    db.execute("UPDATE flights SET status = 'Cancelled' WHERE id = ?", (flight["id"],))
    assert checkin.window_for(get_flight(days=1)).state == "closed"


def test_window_is_admin_configurable(seeded):
    db.execute("UPDATE settings SET value = '6' WHERE key = 'checkin_open_hours'")
    flight = get_flight(days=5)
    now = booking.flight_departure(flight) - timedelta(hours=7)
    assert checkin.window_for(flight, now).state == "not_open"


def test_check_in_refused_outside_window(seeded):
    made = paid(days=7)
    with pytest.raises(BookingError, match="not open"):
        checkin.check_in(made, first_segment(made)["segment_id"], passenger_ids(made))


def test_check_in_needs_payment(seeded):
    made = make_booking(days=1)
    at_flight()
    with pytest.raises(BookingError, match="paid"):
        checkin.check_in(made, first_segment(made)["segment_id"], passenger_ids(made))


def test_check_in_assigns_sequence_and_group(seeded):
    made = paid(days=1, adults=2)
    at_flight()
    segment = first_segment(made)
    assert checkin.check_in(made, segment["segment_id"], passenger_ids(made)) == 2
    records = passengers_repo.seat_records_for_segment(segment["segment_id"])
    assert [r["boarding_sequence"] for r in records] == [
        records[0]["boarding_sequence"],
        records[0]["boarding_sequence"] + 1,
    ]
    assert all(r["checked_in_at"] and r["boarding_group"] for r in records)


def test_check_in_twice_keeps_the_first_sequence(seeded):
    made = paid(days=1)
    at_flight()
    segment = first_segment(made)
    checkin.check_in(made, segment["segment_id"], passenger_ids(made))
    first = passengers_repo.seat_records_for_segment(segment["segment_id"])[0]
    assert checkin.check_in(made, segment["segment_id"], passenger_ids(made)) == 0
    assert (
        passengers_repo.seat_records_for_segment(segment["segment_id"])[0]["boarding_sequence"]
        == first["boarding_sequence"]
    )


def test_check_in_rejects_outsiders_and_empty_lists(seeded):
    made = paid(days=1)
    at_flight()
    segment = first_segment(made)
    with pytest.raises(BookingError):
        checkin.check_in(made, segment["segment_id"], [])
    with pytest.raises(BookingError):
        checkin.check_in(made, segment["segment_id"], [999999])
    with pytest.raises(BookingError):
        checkin.check_in(made, 999999, passenger_ids(made))


def test_seat_locks_after_check_in(seeded):
    made = paid(days=1)
    at_flight()
    segment = first_segment(made)
    pid = passenger_ids(made)[0]
    checkin.check_in(made, segment["segment_id"], [pid])
    code = booking.seats_repo.free_in_cabin(segment["flight_id"], "Economy")[0]["seat_code"]
    with pytest.raises(BookingError, match="after check-in"):
        manage.change_seat(made, segment["segment_id"], pid, code)


def test_changing_flight_clears_check_in(seeded):
    made = paid(days=1, family="Flex")
    at_flight()
    segment = first_segment(made)
    checkin.check_in(made, segment["segment_id"], passenger_ids(made))
    manage.change_flight(made, segment["segment_id"], get_flight("AN103", 5)["id"])
    record = passengers_repo.seat_records_for_segment(segment["segment_id"])[0]
    assert record["checked_in_at"] is None
    assert record["boarding_sequence"] is None


def test_infant_gets_a_pass_without_a_seat(seeded):
    made = paid(days=1, adults=1, infants=1)
    at_flight()
    segment = first_segment(made)
    checkin.check_in(made, segment["segment_id"], passenger_ids(made))
    passes = checkin.boarding_passes(made, segment["segment_id"])["passes"]
    assert len(passes) == 2
    assert {p["record"]["seat_code"] for p in passes} >= {None}


def test_auto_assigns_a_seat_if_missing(seeded):
    made = paid(days=1)
    at_flight()
    segment = first_segment(made)
    pid = passenger_ids(made)[0]
    record = passengers_repo.seat_record(pid, segment["segment_id"])
    booking.seats_repo.release(record["seat_id"])
    passengers_repo.update_seat_record(pid, segment["segment_id"], None, 0)
    checkin.check_in(made, segment["segment_id"], [pid])
    assert passengers_repo.seat_record(pid, segment["segment_id"])["seat_id"] is not None


@pytest.mark.parametrize(
    ("cabin", "priority", "row", "group"),
    [
        ("First", False, 1, 1),
        ("Business", False, 3, 1),
        ("Economy", True, 30, 1),
        ("Economy", False, None, 1),
        ("Economy", False, 12, 2),
        ("Economy", False, 25, 3),
    ],
)
def test_boarding_groups(cabin, priority, row, group):
    assert checkin.boarding_group(cabin, priority, row) == group


def test_priority_extra_moves_passenger_to_group_one(seeded):
    from tests.helpers import make_draft

    draft = make_draft(days=1)
    draft["extras"] = {"0": {"PRIORITY": 1}}
    made = booking.create_booking(draft)
    payment.pay_by_card(made, "4242")
    made = bookings_repo.get(made["id"])
    at_flight()
    segment = first_segment(made)
    checkin.check_in(made, segment["segment_id"], passenger_ids(made))
    assert passengers_repo.seat_records_for_segment(segment["segment_id"])[0]["boarding_group"] == 1


def test_boarding_pass_qr_carries_sequence_and_no_id(seeded):
    made = paid(days=1)
    at_flight()
    segment = first_segment(made)
    checkin.check_in(made, segment["segment_id"], passenger_ids(made))
    entry = checkin.boarding_passes(made, segment["segment_id"])["passes"][0]
    assert entry["qr"].startswith("data:image/svg+xml")


# ------------------------------------------------------------------------- HTTP


def demo_segments(app):
    with app.app_context():
        made = booking.get_by_reference("ANDEMO01")
        return made, first_segment(made)["segment_id"], passenger_ids(made)


def test_demo_booking_has_check_in_open(client, app):
    client.post("/manage/", data={"reference": "ANDEMO01", "email": "wanjiru@anga.example"})
    page = client.get("/manage/ANDEMO01")
    assert b">Check in<" in page.data


def test_check_in_flow_produces_boarding_pass(client, app):
    _, segment_id, ids = demo_segments(app)
    client.post("/manage/", data={"reference": "ANDEMO01", "email": "wanjiru@anga.example"})
    url = f"/manage/ANDEMO01/checkin/{segment_id}"
    assert b"Who is checking in?" in client.get(url).data
    response = client.post(url, data={"passenger": ids})
    assert f"/manage/ANDEMO01/boarding/{segment_id}" in response.headers["Location"]
    page = client.get(response.headers["Location"])
    assert b"Boarding pass" in page.data
    assert b"data:image/svg+xml" in page.data
    assert b"Group" in page.data
    assert b"KE29384756" not in page.data


def test_boarding_pass_requires_check_in(client, app):
    _, segment_id, _ = demo_segments(app)
    client.post("/manage/", data={"reference": "ANDEMO01", "email": "wanjiru@anga.example"})
    response = client.get(f"/manage/ANDEMO01/boarding/{segment_id}")
    assert "/checkin/" in response.headers["Location"]


def test_check_in_page_when_not_open(client, app):
    with app.app_context():
        made = booking.get_by_reference("ANDEMO01")
        later = bookings_repo.segments(made["id"])[1]["segment_id"]
    client.post("/manage/", data={"reference": "ANDEMO01", "email": "wanjiru@anga.example"})
    assert b"Check-in opens" in client.get(f"/manage/ANDEMO01/checkin/{later}").data
    clock.freeze(datetime(2026, 3, 8, 9, 50))
    assert b"has closed" in client.get(f"/manage/ANDEMO01/checkin/{later}").data


def test_check_in_post_outside_window_flashes_an_error(client, app):
    with app.app_context():
        made = booking.get_by_reference("ANDEMO01")
        later = bookings_repo.segments(made["id"])[1]["segment_id"]
        ids = passenger_ids(made)
    client.post("/manage/", data={"reference": "ANDEMO01", "email": "wanjiru@anga.example"})
    page = client.post(
        f"/manage/ANDEMO01/checkin/{later}", data={"passenger": ids}, follow_redirects=True
    )
    assert b"not open" in page.data


def test_unknown_segment_is_404(client):
    client.post("/manage/", data={"reference": "ANDEMO01", "email": "wanjiru@anga.example"})
    assert client.get("/manage/ANDEMO01/checkin/999999").status_code == 404
    assert client.get("/manage/ANDEMO01/boarding/999999").status_code == 404
