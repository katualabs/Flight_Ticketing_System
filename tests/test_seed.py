"""The seed produces a consistent, believable schedule."""

from __future__ import annotations

from datetime import date, timedelta

from anga import clock, db, seed
from anga.repositories import flights as flights_repo
from anga.services import pricing, schedule


def test_airports_and_routes_loaded(seeded):
    assert db.fetch_value("SELECT COUNT(*) FROM airports") == 12
    assert db.fetch_value("SELECT COUNT(*) FROM route_schedules") == len(seed.ROUTES)
    assert db.fetch_value("SELECT COUNT(*) FROM aircraft_types") == 3


def test_every_cabins_buckets_match_its_seat_count(seeded):
    rows = db.fetch_all(
        """
        SELECT f.flight_id, f.cabin, f.total, COUNT(s.id) AS seat_count
        FROM (SELECT flight_id, cabin, SUM(total_seats) AS total FROM fares
              GROUP BY flight_id, cabin) f
        JOIN seats s ON s.flight_id = f.flight_id AND s.cabin = f.cabin
        GROUP BY f.flight_id, f.cabin
        """
    )
    assert rows
    assert all(row["total"] == row["seat_count"] for row in rows)


def test_inventory_matches_free_seats(seeded):
    rows = db.fetch_all(
        """
        SELECT f.flight_id, f.cabin, f.available,
               (SELECT COUNT(*) FROM seats s WHERE s.flight_id = f.flight_id AND s.cabin = f.cabin
                 AND s.blocked = 0 AND s.booking_passenger_id IS NULL) AS free
        FROM (SELECT flight_id, cabin, SUM(available_seats) AS available FROM fares
              GROUP BY flight_id, cabin) f
        """
    )
    assert all(row["available"] == row["free"] for row in rows)


def test_weekday_only_routes_skip_weekends(seeded):
    weekday_only = {
        date.fromisoformat(r["departure_date"]).isoweekday()
        for r in db.fetch_all("SELECT departure_date FROM flights WHERE flight_number = 'AN321'")
    }
    assert weekday_only
    assert weekday_only <= {1, 2, 3, 4, 5}


def test_top_up_does_not_recreate_deleted_flights(seeded):
    today = clock.today()
    target = flights_repo.get_by_number("AN101", (today + timedelta(days=5)).isoformat())
    flights_repo.delete(target["id"])
    schedule.top_up(today, 21)
    assert flights_repo.get(target["id"]) is None


def test_top_up_extends_the_horizon_only_for_new_dates(seeded):
    today = clock.today()
    assert schedule.top_up(today, 21) == 0
    assert schedule.top_up(today, 22) > 0
    assert schedule.top_up(today, 22) == 0


def test_todays_board_has_varied_statuses(seeded):
    statuses = {f["status"] for f in flights_repo.on_date(clock.today().isoformat())}
    assert len(statuses) >= 2
    assert "Scheduled" not in statuses


def test_past_flights_are_landed(seeded):
    yesterday = (clock.today() - timedelta(days=1)).isoformat()
    assert {f["status"] for f in flights_repo.on_date(yesterday)} == {"Landed"}


def test_arrival_time_crosses_timezones():
    assert schedule.arrival_time("15:10", 90, "Africa/Nairobi", "Africa/Kigali") == "15:40"
    assert schedule.arrival_time("08:00", 75, "Africa/Nairobi", "Africa/Nairobi") == "09:15"


def test_partition_always_sums_to_total():
    for total in range(1, 200):
        assert sum(schedule.partition_seats(total).values()) == total


def test_layout_marks_windows_aisles_and_exit_rows():
    _, layout = seed.AIRCRAFT["B738"]
    seats = {seat["code"]: seat for seat in schedule.layout_seats(layout)}
    assert seats["10A"]["is_window"] and not seats["10A"]["is_aisle"]
    assert seats["10C"]["is_aisle"]
    assert seats["18A"]["extra_legroom"] and seats["18A"]["price_extra"] == schedule.EXIT_ROW_PRICE
    assert seats["1A"]["price_extra"] == 0
    assert "13A" not in seats


def test_fares_start_from_route_base_price(seeded):
    flight = flights_repo.get_by_number("AN101", (clock.today() + timedelta(days=3)).isoformat())
    row = db.fetch_one(
        "SELECT price FROM fares WHERE flight_id = ? AND cabin = 'Economy'"
        " AND fare_family = 'Lite'",
        (flight["id"],),
    )
    assert row["price"] == pricing.base_price(8500, "Economy", "Lite")


def test_run_is_idempotent(seeded):
    assert seed.run() is False


def test_fixed_clock_is_in_use(seeded):
    assert clock.today() == date(2026, 3, 2)
