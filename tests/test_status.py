"""Flight status, the airport board, and the contact and destinations pages."""

from __future__ import annotations

from datetime import datetime, timedelta

from anga import clock, db
from anga.repositories import flights as flights_repo
from anga.repositories import messages as messages_repo
from anga.repositories import outbox as outbox_repo
from anga.services import schedule, status
from tests.helpers import TODAY, get_flight


def test_status_by_number(client):
    page = client.get(f"/status?mode=number&number=an101&date={TODAY.isoformat()}")
    assert page.status_code == 200
    assert b"AN101" in page.data
    assert b"<progress" in page.data


def test_status_by_route(client):
    page = client.get(f"/status?mode=route&from=NBO&to=MBA&date={TODAY.isoformat()}")
    assert b"AN101" in page.data
    assert b"AN103" in page.data


def test_status_unknown_flight_shows_empty_state(client):
    page = client.get(f"/status?mode=number&number=AN999&date={TODAY.isoformat()}")
    assert b"No flights found" in page.data


def test_status_bad_flight_number_is_harmless(client):
    page = client.get("/status?mode=number&number=';DROP&date=nonsense")
    assert page.status_code == 200
    assert b"No flights found" in page.data


def test_delay_shifts_estimated_times(seeded):
    flight = get_flight(days=1)
    flights_repo.update_status(flight["id"], "Delayed", 45, "B4")
    result = status.describe(get_flight(days=1))
    assert result.estimated_departure == "08:45"
    assert result.estimated_arrival == "10:00"
    assert result.as_dict()["gate"] == "B4"


def test_progress_line(seeded):
    flight = get_flight(days=1)
    flights_repo.update_status(flight["id"], "Departed", 0, "A1")
    departed = get_flight(days=1)
    clock.freeze(clock.now().replace(day=3, hour=8, minute=30))
    assert status.progress_percent(departed, clock.now()) == 40
    flights_repo.update_status(flight["id"], "Landed", 0, "A1")
    assert status.progress_percent(get_flight(days=1), clock.now()) == 100
    flights_repo.update_status(flight["id"], "Scheduled", 0, None)
    assert status.progress_percent(get_flight(days=1), clock.now()) == 0


def test_board_page_has_departures_and_auto_refresh_hooks(client):
    page = client.get("/status/board/NBO")
    assert page.status_code == 200
    assert b"data-board" in page.data
    assert b'http-equiv="refresh"' in page.data
    assert b"AN101" in page.data


def test_board_arrivals_are_different(client):
    page = client.get("/status/board/NBO?type=arrivals")
    assert b"AN102" in page.data
    assert b"AN101<" not in page.data


def test_board_unknown_airport_is_404(client):
    assert client.get("/status/board/XXX").status_code == 404


def test_board_api_matches_page(client):
    payload = client.get("/api/v1/board/NBO?type=departures").get_json()
    assert payload["ok"] is True
    assert payload["meta"]["airport"] == "NBO"
    assert {"flight_number", "status", "gate", "estimated_departure"} <= set(payload["data"][0])


def test_board_api_validates_type_and_airport(client):
    assert client.get("/api/v1/board/NBO?type=sideways").status_code == 400
    assert client.get("/api/v1/board/XXX").status_code == 404


def test_status_change_appears_on_the_public_board(client, app):
    with app.app_context():
        flight = flights_repo.get_by_number("AN101", TODAY.isoformat())
        flights_repo.update_status(flight["id"], "Delayed", 90, "C9")
    page = client.get("/status/board/NBO")
    assert b"C9" in page.data
    assert b"+90m" in page.data


def test_statuses_advance_with_the_clock(seeded):
    flight = flights_repo.get_by_number("AN103", TODAY.isoformat())
    assert flight["status"] in ("On time", "Delayed")
    delay = flight["delay_minutes"]
    clock.freeze(datetime(2026, 3, 2, 17, 45) + timedelta(minutes=delay))
    schedule.advance_board(clock.now())
    assert flights_repo.get(flight["id"])["status"] == "Departed"
    clock.freeze(datetime(2026, 3, 2, 19, 0) + timedelta(minutes=delay))
    schedule.advance_board(clock.now())
    assert flights_repo.get(flight["id"])["status"] == "Landed"


def test_simulation_never_overrides_staff(seeded):
    flight = flights_repo.get_by_number("AN103", TODAY.isoformat())
    flights_repo.update_status(flight["id"], "Delayed", 120, "C3")
    clock.freeze(datetime(2026, 3, 2, 23, 0))
    schedule.advance_board(clock.now())
    after = flights_repo.get(flight["id"])
    assert (after["status"], after["delay_minutes"], after["gate"]) == ("Delayed", 120, "C3")


def test_board_stays_useful_late_at_night(seeded):
    clock.freeze(datetime(2026, 3, 2, 23, 30))
    schedule.advance_board(clock.now())
    rows = status.board("NBO", "departures", clock.today())
    assert rows
    assert {row.flight["departure_date"] for row in rows} == {"2026-03-03"}
    assert {row.status for row in rows} <= {"On time", "Delayed"}
    assert all(row.gate for row in rows)


def test_destinations_page(client):
    page = client.get("/destinations")
    assert b"Zanzibar" in page.data
    assert b"destinations/znz.svg" in page.data


def test_contact_saves_message_and_copies_to_outbox(client, app):
    response = client.post(
        "/contact",
        data={
            "full_name": "Zawadi Mwita",
            "email": "zawadi@example.com",
            "subject": "Hello there",
            "body": "A message that is long enough.",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        assert (
            db.fetch_value(
                "SELECT COUNT(*) FROM contact_messages WHERE email = 'zawadi@example.com'"
            )
            == 1
        )
        assert outbox_repo.for_recipient("hello@anga.example")
        assert messages_repo.unread_count() >= 1


def test_contact_validation(client):
    page = client.post(
        "/contact", data={"full_name": "x", "email": "bad", "subject": "", "body": ""}
    )
    assert page.status_code == 400
    assert b"valid email" in page.data
