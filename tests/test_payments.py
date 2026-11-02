"""Simulated payments, confirmation, e-tickets and the outbox."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from anga import clock, db, validators
from anga.repositories import bookings as bookings_repo
from anga.repositories import outbox as outbox_repo
from anga.repositories import payments as payments_repo
from anga.services import loyalty, payment, tickets
from anga.services.payment import PaymentError
from tests.helpers import get_fare, get_flight, make_booking

TODAY = date(2026, 3, 2)
CARD = {
    "method": "card_sim",
    "card_number": "4242 4242 4242 4242",
    "card_expiry": "12/30",
    "card_cvc": "123",
    "card_name": "Amina Otieno",
}


def reach_payment(client, app, **fare):
    with app.app_context():
        fare_id = get_fare(**fare)["id"]
    client.post(
        "/book/start",
        data={
            "outbound_fare": fare_id,
            "adults": 1,
            "children": 0,
            "infants": 0,
            "trip": "one_way",
        },
    )
    client.post(
        "/book/passengers",
        data={
            "name_0": "Amina Otieno",
            "id_0": "A1234567",
            "email": "amina@example.com",
            "phone": "+254712345678",
        },
    )


def latest_booking(app):
    with app.app_context():
        return db.fetch_one("SELECT * FROM bookings ORDER BY id DESC LIMIT 1")


def booking_count(app):
    with app.app_context():
        return db.fetch_value("SELECT COUNT(*) FROM bookings")


def test_pay_page_shows_every_method_and_the_simulation_notice(client, app):
    reach_payment(client, app)
    page = client.get("/book/pay")
    assert b"M-Pesa" in page.data
    assert b"4242 4242 4242 4242" in page.data
    assert b"Pay later" in page.data
    assert b"simulated" in page.data


def test_full_wizard_happy_path_with_demo_card(client, app):
    reach_payment(client, app)
    client.post("/book/seats", data={"step": "seats"})
    client.post("/book/extras", data={"bag_0": "1", "meal_0": "MEAL_VEG"})
    assert client.get("/book/review").status_code == 200
    response = client.post("/book/pay", data=CARD)
    assert response.status_code == 302
    booking = latest_booking(app)
    assert booking["status"] == "Confirmed"
    assert booking["extras_total"] == 2500 + 850
    page = client.get(response.headers["Location"])
    assert booking["reference"].encode() in page.data
    assert b"You are all set" in page.data
    assert b"data:image/svg+xml" in page.data
    assert b"Extra 23 kg bag" in page.data
    assert b"A1234567" not in page.data


def test_card_stores_only_last_four(client, app):
    reach_payment(client, app)
    client.post("/book/pay", data=CARD)
    with app.app_context():
        booking = latest_booking(app)
        row = payments_repo.for_booking(booking["id"])[0]
        assert row["card_last4"] == "4242"
        assert row["status"] == "succeeded"
        everything = " ".join(str(value) for value in dict(row).values())
    assert "4242424242424242" not in everything


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("card_number", "5555 5555 5555 4444", b"only accepts the test card"),
        ("card_expiry", "01/20", b"expired"),
        ("card_expiry", "13/40", b"MM/YY"),
        ("card_cvc", "12", b"3-digit"),
        ("card_name", "", b"name on the card"),
    ],
)
def test_demo_card_rules(client, app, field, value, fragment):
    reach_payment(client, app)
    before = booking_count(app)
    page = client.post("/book/pay", data={**CARD, field: value})
    assert page.status_code == 400
    assert fragment in page.data
    assert booking_count(app) == before


def test_card_never_echoes_the_number_or_cvc(client, app):
    reach_payment(client, app)
    page = client.post("/book/pay", data={**CARD, "card_expiry": "bad"})
    assert b'value="4242 4242 4242 4242"' not in page.data
    assert b'value="123"' not in page.data


def test_mpesa_success_flow(client, app):
    reach_payment(client, app)
    response = client.post("/book/pay", data={"method": "mpesa", "mpesa_phone": "0712345678"})
    assert "/book/mpesa/" in response.headers["Location"]
    reference = response.headers["Location"].rsplit("/", 1)[1]
    status = client.get(f"/book/payment-status/{reference}").get_json()
    assert status["status"] == "succeeded"
    assert latest_booking(app)["status"] == "Confirmed"
    done = client.get(f"/book/mpesa/{reference}")
    assert done.status_code == 302
    assert "/book/confirmation/" in done.headers["Location"]


def test_mpesa_failure_keeps_the_hold_and_allows_retry(client, app):
    reach_payment(client, app)
    response = client.post("/book/pay", data={"method": "mpesa", "mpesa_phone": "0712345000"})
    reference = response.headers["Location"].rsplit("/", 1)[1]
    assert client.get(f"/book/payment-status/{reference}").get_json()["status"] == "failed"
    booking = latest_booking(app)
    assert booking["status"] == "Pending"
    page = client.get(f"/book/mpesa/{reference}")
    assert b"did not go through" in page.data
    retry = client.post(
        f"/book/pay/{booking['reference']}", data={"method": "mpesa", "mpesa_phone": "0712345678"}
    )
    new_ref = retry.headers["Location"].rsplit("/", 1)[1]
    assert client.get(f"/book/payment-status/{new_ref}").get_json()["status"] == "succeeded"
    assert latest_booking(app)["status"] == "Confirmed"


def test_mpesa_waits_for_the_simulated_delay(client, app):
    app.config["MPESA_SIM_SECONDS"] = 5
    reach_payment(client, app)
    response = client.post("/book/pay", data={"method": "mpesa", "mpesa_phone": "0712345678"})
    reference = response.headers["Location"].rsplit("/", 1)[1]
    assert client.get(f"/book/payment-status/{reference}").get_json()["status"] == "initiated"
    page = client.get(f"/book/mpesa/{reference}")
    assert b"Check your phone" in page.data
    assert b"data-payment-poll" in page.data
    clock.freeze(clock.now() + timedelta(seconds=6))
    assert client.get(f"/book/payment-status/{reference}").get_json()["status"] == "succeeded"


def test_invalid_mpesa_phone_is_rejected(client, app):
    reach_payment(client, app)
    page = client.post("/book/pay", data={"method": "mpesa", "mpesa_phone": "12345"})
    assert page.status_code == 400
    assert b"Kenyan mobile number" in page.data


def test_polling_twice_confirms_once(seeded):
    booking = make_booking()
    pay = payment.initiate_mpesa(booking, "0712345678")
    clock.freeze(clock.now() + timedelta(minutes=1))
    payment.poll_mpesa(pay)
    payment.poll_mpesa(payments_repo.get_by_reference(pay["reference"]))
    assert len(outbox_repo.for_recipient(booking["contact_email"])) == 1


def test_mpesa_settling_after_expiry_fails(seeded):
    booking = make_booking()
    pay = payment.initiate_mpesa(booking, "0712345678")
    bookings_repo.cancel(booking["id"], clock.timestamp())
    clock.freeze(clock.now() + timedelta(minutes=1))
    assert payment.poll_mpesa(pay)["status"] == "failed"


def test_pay_later_holds_for_24_hours_then_expires(client, app):
    reach_payment(client, app)
    response = client.post("/book/pay", data={"method": "pay_later"})
    assert response.status_code == 302
    booking = latest_booking(app)
    assert booking["status"] == "Pending"
    assert booking["expires_at"] == (clock.now() + timedelta(hours=24)).isoformat(
        timespec="seconds"
    )
    page = client.get(response.headers["Location"])
    assert b"Your seats are held" in page.data
    assert b"Pay now" in page.data
    assert b"data:image/svg+xml" not in page.data
    clock.freeze(clock.now() + timedelta(hours=25))
    client.get("/about")
    assert latest_booking(app)["status"] == "Cancelled"


def test_pay_later_is_refused_close_to_departure(seeded):
    flight = get_flight("AN103", 0)
    with pytest.raises(PaymentError):
        clock.freeze(datetime(2026, 3, 2, 13, 0))
        payment.pay_later_expiry([flight])


def test_pay_later_deadline_never_passes_the_flight(seeded):
    flight = get_flight("AN101", 1)
    deadline = payment.pay_later_expiry([flight])
    assert deadline == datetime(2026, 3, 3, 2, 0)


def test_held_booking_can_be_paid_by_card_later(client, app):
    reach_payment(client, app)
    client.post("/book/pay", data={"method": "pay_later"})
    booking = latest_booking(app)
    page = client.get(f"/book/pay/{booking['reference']}")
    assert page.status_code == 200
    assert b"Pay later" not in page.data
    client.post(f"/book/pay/{booking['reference']}", data=CARD)
    assert latest_booking(app)["status"] == "Confirmed"


def test_expected_total_mismatch_sends_customer_back_to_review(client, app):
    reach_payment(client, app)
    before = booking_count(app)
    response = client.post("/book/pay", data={**CARD, "expected_total": "1"})
    assert "/book/review" in response.headers["Location"]
    assert booking_count(app) == before


def test_other_visitors_cannot_see_a_confirmation(client, app):
    reach_payment(client, app)
    client.post("/book/pay", data=CARD)
    reference = latest_booking(app)["reference"]
    assert client.get(f"/book/confirmation/{reference}").status_code == 200
    stranger = app.test_client()
    assert stranger.get(f"/book/confirmation/{reference}").status_code == 404
    assert stranger.get(f"/book/pay/{reference}").status_code == 404


def test_confirmation_email_written_to_outbox(seeded):
    booking = make_booking()
    payment.pay_by_card(booking, "4242")
    messages = outbox_repo.for_recipient(booking["contact_email"])
    assert len(messages) == 1
    assert booking["reference"] in messages[0]["subject"]
    assert booking["reference"] in messages[0]["html_body"]
    assert "AN101" in messages[0]["html_body"]


def test_paid_booking_cannot_be_paid_again(seeded):
    booking = make_booking()
    payment.pay_by_card(booking, "4242")
    confirmed = bookings_repo.get(booking["id"])
    with pytest.raises(PaymentError):
        payment.pay_by_card(confirmed, "4242")
    with pytest.raises(PaymentError):
        payment.initiate_mpesa(confirmed, "0712345678")


def test_amount_paid_nets_refunds(seeded):
    booking = make_booking()
    payment.pay_by_card(booking, "4242")
    confirmed = bookings_repo.get(booking["id"])
    assert payments_repo.amount_paid(booking["id"]) == confirmed["total"]
    payment.record_refund(confirmed, 1000)
    assert payments_repo.amount_paid(booking["id"]) == confirmed["total"] - 1000


def test_ticket_qr_payload_has_no_id_number(seeded):
    booking = make_booking()
    payment.pay_by_card(booking, "4242")
    detail = tickets.booking_detail(bookings_repo.get(booking["id"]))
    entry = detail["segments"][0]["tickets"][0]
    payload = tickets.ticket_payload(
        detail["booking"], detail["segments"][0]["flight"], entry["record"]
    )
    assert payload.startswith(f"ANGA|{booking['reference']}|AN101|")
    assert entry["record"]["id_number"] not in payload
    assert entry["qr"].startswith("data:image/svg+xml")


@pytest.mark.parametrize(
    ("phone", "ok"),
    [
        ("0712345678", True),
        ("0112345678", True),
        ("+254712345678", True),
        ("254 712 345 678", True),
        ("0812345678", False),
        ("071234567", False),
        ("nonsense", False),
    ],
)
def test_mpesa_phone_formats(phone, ok):
    assert (validators.validate_mpesa_phone(phone)[1] is None) is ok


def test_miles_arithmetic_and_tiers():
    assert loyalty.miles_for(8550) == 85
    assert loyalty.miles_for(-5) == 0
    assert loyalty.tier_for(0).name == "Member"
    assert loyalty.tier_for(499).miles_to_next == 1
    assert loyalty.tier_for(500).name == "Silver"
    assert loyalty.tier_for(2000).name == "Gold"
    assert loyalty.tier_for(2000).next_name is None
