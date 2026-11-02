"""Accounts: registration, sign-in, lockout, travellers, miles and price watches."""

from __future__ import annotations

from datetime import timedelta

import pytest

from anga import clock, db, validators
from anga.repositories import outbox as outbox_repo
from anga.services import accounts, booking, payment, watches
from tests.helpers import future_date, get_flight, make_draft

PASSWORD = "Sunny#Coast2026"
REGISTRATION = {
    "full_name": "Amina Otieno",
    "email": "amina@example.com",
    "phone": "+254712345678",
    "password": PASSWORD,
    "confirm_password": PASSWORD,
}


def login(client, email="wanjiru@anga.example", password="AngaFly#2026", **extra):
    return client.post("/account/login", data={"email": email, "password": password, **extra})


# ----------------------------------------------------------------- registration


def test_register_logs_in_and_hashes_the_password(client, app):
    response = client.post("/account/register", data=REGISTRATION)
    assert response.status_code == 302
    assert b"Karibu" in client.get("/account/").data
    with app.app_context():
        stored = db.fetch_value("SELECT password_hash FROM users WHERE email = 'amina@example.com'")
    assert PASSWORD not in stored
    assert stored.startswith("pbkdf2:")


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("full_name", "Amina", b"first and last name"),
        ("email", "not-an-email", b"valid email"),
        ("phone", "12", b"valid phone"),
        ("password", "short", b"at least 10"),
        ("password", "alllowercase1!", b"upper and lower"),
        ("confirm_password", "Different#2026", b"do not match"),
    ],
)
def test_register_validation(client, field, value, fragment):
    page = client.post("/account/register", data={**REGISTRATION, field: value})
    assert page.status_code == 400
    assert fragment in page.data


def test_registration_does_not_echo_the_password(client):
    page = client.post("/account/register", data={**REGISTRATION, "email": "bad"})
    assert PASSWORD.encode() not in page.data


def test_duplicate_email_is_rejected(client):
    page = client.post("/account/register", data={**REGISTRATION, "email": "WANJIRU@anga.example"})
    assert page.status_code == 400
    assert b"already exists" in page.data


def test_phone_is_optional(client):
    assert client.post("/account/register", data={**REGISTRATION, "phone": ""}).status_code == 302


# --------------------------------------------------------------- login / logout


def test_login_and_logout(client):
    assert login(client).status_code == 302
    assert b"Wanjiru" in client.get("/account/").data
    response = client.post("/account/logout")
    assert response.status_code == 302
    assert client.get("/account/").status_code == 302


def test_logout_requires_post(client):
    login(client)
    assert client.get("/account/logout").status_code == 405


def test_wrong_password_and_unknown_email_look_the_same(client):
    wrong = login(client, password="Wrong#Password1")
    unknown = login(client, email="nobody@example.com", password="Wrong#Password1")
    assert wrong.status_code == unknown.status_code == 401
    assert b"do not match" in wrong.data
    assert b"do not match" in unknown.data


def test_login_rotates_the_session(client):
    with client.session_transaction() as session:
        session["planted"] = "by-an-attacker"
    login(client)
    with client.session_transaction() as session:
        assert "planted" not in session
        assert session["user_id"]


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        login(client, password="Wrong#Password1")
    page = login(client)
    assert page.status_code == 401
    assert b"Too many failed attempts" in page.data
    clock.freeze(clock.now() + timedelta(minutes=16))
    assert login(client).status_code == 302


def test_successful_login_resets_the_failure_count(client):
    for _ in range(4):
        login(client, password="Wrong#Password1")
    assert login(client).status_code == 302
    client.post("/account/logout")
    for _ in range(4):
        assert b"do not match" in login(client, password="Wrong#Password1").data


def test_disabled_account_cannot_log_in_and_is_signed_out(client, app):
    login(client)
    with app.app_context():
        db.execute("UPDATE users SET disabled = 1 WHERE email = 'wanjiru@anga.example'")
    assert client.get("/account/").status_code == 302
    assert login(client).status_code == 401


@pytest.mark.parametrize(
    ("target", "fragment"),
    [
        ("/manage/", "/manage/"),
        ("https://evil.example/", "/account/"),
        ("//evil.example", "/account/"),
    ],
)
def test_next_redirect_is_local_only(client, target, fragment):
    response = login(client, next=target)
    assert response.headers["Location"].startswith(fragment)


def test_account_pages_need_login_and_are_not_cached(client):
    for path in ("/account/", "/account/travellers", "/account/miles", "/account/profile"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/account/login" in response.headers["Location"]
        assert response.headers["Cache-Control"] == "no-store"


def test_logged_in_user_skips_login_and_register(client):
    login(client)
    assert client.get("/account/login").status_code == 302
    assert client.get("/account/register").status_code == 302


# -------------------------------------------------------------------- dashboard


def test_dashboard_lists_trips_miles_and_tier(client):
    login(client)
    page = client.get("/account/")
    assert b"ANDEMO01" in page.data
    assert b"ANDEMO02" in page.data
    assert b"Silver" in page.data
    assert b"Past and cancelled trips" in page.data


def test_owner_can_open_their_booking_without_the_email_step(client):
    login(client)
    assert client.get("/manage/ANDEMO01").status_code == 200


def test_another_customer_cannot_open_it(client):
    client.post("/account/register", data=REGISTRATION)
    assert client.get("/manage/ANDEMO01").status_code == 404
    assert client.get("/book/confirmation/ANDEMO01").status_code == 404


def test_new_customer_sees_an_empty_state(client):
    client.post("/account/register", data=REGISTRATION)
    assert b"No trips booked yet" in client.get("/account/").data


# ---------------------------------------------------------------------- profile


def test_profile_update(client):
    login(client)
    response = client.post(
        "/account/profile", data={"full_name": "Wanjiru Njoroge", "phone": "+254711111111"}
    )
    assert response.status_code == 302
    assert b"Wanjiru Njoroge" in client.get("/account/profile").data
    assert client.post("/account/profile", data={"full_name": "x"}).status_code == 400


def test_password_change(client):
    login(client)
    new = "Fresh#Password2026"
    bad = client.post(
        "/account/password",
        data={"current_password": "wrong", "password": new, "confirm_password": new},
    )
    assert bad.status_code == 400
    assert b"current password" in bad.data
    weak = client.post(
        "/account/password",
        data={"current_password": "AngaFly#2026", "password": "weak", "confirm_password": "weak"},
    )
    assert weak.status_code == 400
    good = client.post(
        "/account/password",
        data={"current_password": "AngaFly#2026", "password": new, "confirm_password": new},
    )
    assert good.status_code == 302
    client.post("/account/logout")
    assert login(client).status_code == 401
    assert login(client, password=new).status_code == 302


# -------------------------------------------------------------- saved travellers


def test_add_and_remove_traveller(client, app):
    login(client)
    response = client.post(
        "/account/travellers",
        data={"full_name": "Juma Kamau", "id_number": "KE11112222", "date_of_birth": "1990-01-01"},
    )
    assert response.status_code == 302
    page = client.get("/account/travellers")
    assert b"Juma Kamau" in page.data
    assert b"KE11112222" not in page.data
    with app.app_context():
        traveller_id = db.fetch_value(
            "SELECT id FROM saved_travellers WHERE full_name = 'Juma Kamau'"
        )
    assert client.post(f"/account/travellers/{traveller_id}/delete").status_code == 302
    assert b"Juma Kamau" not in client.get("/account/travellers").data


def test_traveller_validation(client):
    login(client)
    page = client.post(
        "/account/travellers", data={"full_name": "x", "id_number": "1", "date_of_birth": "nope"}
    )
    assert page.status_code == 400
    assert b"valid date" in page.data


def test_cannot_delete_another_customers_traveller(client, app):
    with app.app_context():
        foreign = db.fetch_value("SELECT id FROM saved_travellers LIMIT 1")
    client.post("/account/register", data=REGISTRATION)
    assert client.post(f"/account/travellers/{foreign}/delete").status_code == 404


def test_wizard_offers_saved_travellers(client, app):
    login(client)
    with app.app_context():
        fare_id = booking.fares_repo.get(get_flight()["id"], "Economy", "Classic")["id"]
    client.post("/book/start", data={"outbound_fare": fare_id, "adults": 1, "trip": "one_way"})
    page = client.get("/book/passengers")
    assert b"data-traveller-picker" in page.data
    assert b"Daudi Kamau" in page.data


# ------------------------------------------------------------------------ miles


def test_booking_while_logged_in_earns_miles_and_ledger_entry(client, app):
    login(client)
    with app.app_context():
        user_id = db.fetch_value("SELECT id FROM users WHERE email = 'wanjiru@anga.example'")
        before = db.fetch_value("SELECT miles_balance FROM users WHERE id = ?", (user_id,))
        made = booking.create_booking(make_draft(family="Flex"), user_id=user_id)
        payment.pay_by_card(made, "4242")
        after = db.fetch_value("SELECT miles_balance FROM users WHERE id = ?", (user_id,))
    assert after - before == made["total"] // 100
    assert made["reference"].encode() in client.get("/account/miles").data


def test_guest_booking_earns_nothing(seeded):
    made = booking.create_booking(make_draft())
    before = db.fetch_value("SELECT COALESCE(SUM(delta), 0) FROM miles_ledger")
    payment.pay_by_card(made, "4242")
    assert db.fetch_value("SELECT COALESCE(SUM(delta), 0) FROM miles_ledger") == before


def test_pending_booking_earns_nothing_until_paid(seeded):
    user_id = db.fetch_value("SELECT id FROM users WHERE email = 'wanjiru@anga.example'")
    before = db.fetch_value("SELECT miles_balance FROM users WHERE id = ?", (user_id,))
    booking.create_booking(make_draft(), user_id=user_id)
    assert db.fetch_value("SELECT miles_balance FROM users WHERE id = ?", (user_id,)) == before


# ---------------------------------------------------------------- price watching


def cheapen(flight_number="AN101", days=7):
    """Make a flight emptier, which pushes its live fare back down."""
    flight = get_flight(flight_number, days)
    db.execute("UPDATE fares SET price = price / 2 WHERE flight_id = ?", (flight["id"],))


def test_watch_button_only_for_logged_in_users(client):
    url = f"/search/?from=NBO&to=MBA&depart={future_date()}&trip=one_way&adults=1"
    assert b"Watch this price" not in client.get(url).data
    login(client)
    assert b"Watch this price" in client.get(url).data


def test_price_drop_raises_alert_email_and_dashboard_banner(client, app):
    login(client)
    response = client.post(
        "/account/watches",
        data={"from": "NBO", "to": "MBA", "date": future_date(), "cabin": "Economy"},
        follow_redirects=True,
    )
    assert b"Watching this trip" in response.data
    assert b"Price drop!" not in client.get("/account/").data
    with app.app_context():
        cheapen()
        cheapen("AN103")
    assert b"Price drop!" in client.get("/account/").data
    with app.app_context():
        emails = outbox_repo.for_recipient("wanjiru@anga.example")
        assert "Price drop" in emails[0]["subject"]


def test_watch_alerts_only_once(seeded):
    user_id = db.fetch_value("SELECT id FROM users WHERE email = 'wanjiru@anga.example'")
    day = clock.today() + timedelta(days=7)
    watches.create(user_id, "NBO", "MBA", day, "Economy")
    assert watches.check() == 0
    cheapen()
    cheapen("AN103")
    assert watches.check() == 1
    assert watches.check() == 0


def test_rewatching_restarts_from_the_new_price(seeded):
    user_id = db.fetch_value("SELECT id FROM users WHERE email = 'wanjiru@anga.example'")
    day = clock.today() + timedelta(days=7)
    watches.create(user_id, "NBO", "MBA", day, "Economy")
    cheapen()
    cheapen("AN103")
    watches.check()
    watches.create(user_id, "NBO", "MBA", day, "Economy")
    assert watches.check() == 0
    assert len(watches.for_user(user_id)) == 1


def test_watch_validation(client):
    login(client)
    past = client.post(
        "/account/watches",
        data={"from": "NBO", "to": "MBA", "date": "2020-01-01"},
        follow_redirects=True,
    )
    assert b"future date" in past.data
    empty = client.post(
        "/account/watches",
        data={"from": "NBO", "to": "NBO", "date": future_date()},
        follow_redirects=True,
    )
    assert b"no fares to watch" in empty.data


def test_dismiss_watch_is_owner_only(client, app):
    with app.app_context():
        user_id = db.fetch_value("SELECT id FROM users WHERE email = 'wanjiru@anga.example'")
        watches.create(user_id, "NBO", "MBA", clock.today() + timedelta(days=7), "Economy")
        watch_id = db.fetch_value("SELECT id FROM price_watches")
    client.post("/account/register", data=REGISTRATION)
    assert client.post(f"/account/watches/{watch_id}/dismiss").status_code == 404
    client.post("/account/logout")
    login(client)
    assert client.post(f"/account/watches/{watch_id}/dismiss").status_code == 302
    assert b"AN101" not in client.get("/account/miles").data


def test_cli_commands(app):
    runner = app.test_cli_runner()
    assert "alert" in runner.invoke(args=["check-price-watches"]).output
    assert "Expired" in runner.invoke(args=["expire-holds"]).output
    assert "up to date" in runner.invoke(args=["init-db"]).output
    assert "already seeded" in runner.invoke(args=["seed"]).output


def test_validate_password_rules():
    assert validators.password_problem("Strong#Pass2026") is None
    assert validators.password_problem("x" * 200)
    assert accounts.AccountError
