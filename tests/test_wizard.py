"""The booking wizard over HTTP."""

from __future__ import annotations

from tests.helpers import future_date, get_fare


def start_wizard(client, app, **overrides):
    with app.app_context():
        fare_id = get_fare(**overrides)["id"]
    return client.post(
        "/book/start",
        data={
            "outbound_fare": fare_id,
            "adults": 1,
            "children": 0,
            "infants": 0,
            "trip": "one_way",
        },
    )


def fill_passengers(client):
    return client.post(
        "/book/passengers",
        data={
            "name_0": "Amina Otieno",
            "id_0": "A1234567",
            "email": "amina@example.com",
            "phone": "+254712345678",
        },
    )


def test_results_page_offers_a_selection_form(client):
    page = client.get(f"/search/?from=NBO&to=MBA&depart={future_date()}&trip=one_way&adults=1")
    assert b'name="outbound_fare"' in page.data
    assert b'action="/book/start"' in page.data


def test_wizard_requires_a_draft(client):
    assert client.get("/book/passengers").status_code == 302


def test_start_rejects_missing_fare(client):
    response = client.post("/book/start", data={"adults": 1, "trip": "one_way"})
    assert response.status_code == 302
    assert client.get("/book/passengers").status_code == 302


def test_start_requires_return_for_round_trip(client, app):
    with app.app_context():
        fare_id = get_fare()["id"]
    client.post("/book/start", data={"outbound_fare": fare_id, "adults": 1, "trip": "round_trip"})
    assert client.get("/book/passengers").status_code == 302


def test_passenger_step_shows_validation_errors(client, app):
    start_wizard(client, app)
    page = client.post("/book/passengers", data={"name_0": "x", "email": "nope"})
    assert page.status_code == 400
    assert b"valid email" in page.data
    assert b"full name" in page.data


def test_later_steps_need_passengers_first(client, app):
    start_wizard(client, app)
    for path in ("/book/seats", "/book/extras", "/book/review"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/book/passengers" in response.headers["Location"]


def test_wizard_walks_through_seats_extras_and_review(client, app):
    start_wizard(client, app)
    assert fill_passengers(client).status_code == 302
    seats_page = client.get("/book/seats")
    assert b"data-seat=" in seats_page.data
    assert b"data-seatmap" in seats_page.data
    assert client.post("/book/seats", data={"step": "seats"}).status_code == 302
    assert b"Extra 23 kg bag" in client.get("/book/extras").data
    assert client.post("/book/extras", data={"bag_0": "1"}).status_code == 302
    review = client.get("/book/review")
    assert b"Extra 23 kg bag" in review.data
    assert b"KSh" in review.data
    # ID numbers are masked even on the customer's own review page.
    assert b"A1234567" not in review.data


def test_taken_seat_is_refused_at_the_seat_step(client, app):
    start_wizard(client, app)
    fill_passengers(client)
    page = client.post("/book/seats", data={"seat_0_0": "99Z"})
    assert page.status_code == 409
    assert b"just been taken" in page.data


def test_review_applies_and_removes_promo(client, app):
    start_wizard(client, app)
    fill_passengers(client)
    page = client.post(
        "/book/review", data={"action": "apply_promo", "promo": "COAST2026"}, follow_redirects=True
    )
    assert b"applied" in page.data
    assert b"COAST2026" in page.data
    removed = client.post("/book/review", data={"action": "remove_promo"}, follow_redirects=True)
    assert b"Remove" not in removed.data


def test_bad_promo_shows_a_clear_message(client, app):
    start_wizard(client, app)
    fill_passengers(client)
    page = client.post(
        "/book/review", data={"action": "apply_promo", "promo": "NOPE"}, follow_redirects=True
    )
    assert b"not valid" in page.data


def test_live_quote_endpoint_reprices_without_saving(client, app):
    start_wizard(client, app)
    fill_passengers(client)
    response = client.post("/book/quote", data={"step": "extras", "bag_0": "1"})
    assert response.status_code == 200
    assert b"Extra 23 kg bag" in response.data
    assert b"Extra 23 kg bag" not in client.get("/book/seats").data


def test_booking_pages_are_not_cached(client, app):
    start_wizard(client, app)
    assert client.get("/book/passengers").headers["Cache-Control"] == "no-store"
