"""Flight search, filters, fare calendar and the home page's live data."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from anga import clock, db, validators
from anga.services import search

TODAY = date(2026, 3, 2)


def search_url(**overrides) -> str:
    params = {
        "from": "NBO",
        "to": "MBA",
        "depart": (TODAY + timedelta(days=4)).isoformat(),
        "trip": "one_way",
        "cabin": "Economy",
        "adults": "1",
    }
    params.update(overrides)
    return "/search/?" + "&".join(f"{key}={value}" for key, value in params.items())


def test_results_list_flights_and_fare_families(client):
    page = client.get(search_url())
    assert page.status_code == 200
    assert b"AN101" in page.data
    assert b"AN103" in page.data
    for family in (b"Lite", b"Classic", b"Flex"):
        assert family in page.data


def test_no_results_suggests_nearby_dates(client):
    # AN321 is weekdays-only, so a Sunday has no flights but its neighbours do.
    page = client.get(search_url(to="JRO", depart="2026-03-08"))
    assert page.status_code == 200
    assert b"No flights match" in page.data
    assert b"Fares on nearby dates" in page.data


def test_past_date_is_rejected(client):
    page = client.get(search_url(depart="2026-03-01"))
    assert page.status_code == 400
    assert b"cannot be in the past" in page.data


def test_same_origin_and_destination_is_rejected(client):
    page = client.get(search_url(to="NBO"))
    assert page.status_code == 400
    assert b"must be different" in page.data


def test_round_trip_requires_a_valid_return(client):
    page = client.get(search_url(trip="round_trip"))
    assert page.status_code == 400
    assert b"Choose a return date" in page.data
    early = client.get(search_url(trip="round_trip", **{"return": "2026-03-03"}))
    assert b"cannot be before departure" in early.data


def test_round_trip_shows_return_flights(client):
    page = client.get(search_url(trip="round_trip", **{"return": "2026-03-10"}))
    assert page.status_code == 200
    assert b"AN102" in page.data


def test_infants_cannot_outnumber_adults(client):
    page = client.get(search_url(infants="2"))
    assert b"lap" in page.data
    assert page.status_code == 400


def test_flights_that_have_left_are_not_offered(seeded):
    # The clock is frozen at 10:00, after AN101 (08:00) but before AN103 (17:30).
    options = search.search_flights("NBO", "MBA", TODAY, "Economy", 1)
    assert [o.flight["flight_number"] for o in options] == ["AN103"]


def test_calendar_price_for_today_ignores_departed_flights(seeded):
    clock.freeze(clock.now().replace(hour=23))
    result = search.fare_calendar("NBO", "MBA", date(2026, 3, 1), "Economy", TODAY)
    today_cell = next(c for week in result.weeks for c in week if c and c.day == TODAY)
    assert today_cell.price is None


def test_filter_by_time_of_day(seeded):
    day = TODAY + timedelta(days=4)
    options = search.search_flights("NBO", "MBA", day, "Economy", 1, time_of_day="evening")
    assert [o.flight["flight_number"] for o in options] == ["AN103"]


def test_filter_by_max_price(seeded):
    day = TODAY + timedelta(days=4)
    assert search.search_flights("NBO", "MBA", day, "Economy", 1, max_price=100) == []


def test_sort_orders(seeded):
    day = TODAY + timedelta(days=4)
    by_time = search.search_flights("NBO", "MBA", day, "Economy", 1, sort="departure")
    assert [o.flight["departure_time"] for o in by_time] == ["08:00", "17:30"]
    by_price = search.search_flights("NBO", "MBA", day, "Economy", 1, sort="price")
    prices = [o.cheapest for o in by_price]
    assert prices == sorted(prices)


def test_cabin_filter_limits_fares(seeded):
    day = TODAY + timedelta(days=4)
    options = search.search_flights("NBO", "MBA", day, "First", 1)
    assert {fare.cabin for option in options for fare in option.fares} == {"First"}


def test_dash8_has_no_first_class(seeded):
    assert search.search_flights("NBO", "UKA", TODAY + timedelta(days=4), "First", 1) == []


def test_party_larger_than_bucket_marks_fare_unavailable(seeded):
    day = TODAY + timedelta(days=4)
    options = search.search_flights("NBO", "MBA", day, "First", 9)
    assert all(fare.seats_left == 0 for option in options for fare in option.fares)


def test_low_seat_badge(seeded):
    db.execute("UPDATE fares SET available_seats = 3 WHERE cabin = 'Economy'")
    day = TODAY + timedelta(days=4)
    option = search.search_flights("NBO", "MBA", day, "Economy", 1)[0]
    assert option.fares[0].low_stock is True


def test_demand_raises_the_price(seeded):
    day = TODAY + timedelta(days=4)
    before = search.cheapest_on("NBO", "MBA", day, "Economy")
    db.execute(
        "UPDATE fares SET available_seats = CAST(total_seats * 0.1 AS INTEGER)"
        " WHERE cabin = 'Economy'"
    )
    assert search.cheapest_on("NBO", "MBA", day, "Economy") > before


def test_cancelled_flights_are_not_offered(seeded):
    day = TODAY + timedelta(days=4)
    db.execute(
        "UPDATE flights SET status = 'Cancelled' WHERE departure_date = ?", (day.isoformat(),)
    )
    assert search.search_flights("NBO", "MBA", day, "Economy", 1) == []


def test_fare_calendar_page_renders_clickable_days(client):
    page = client.get("/search/calendar?from=NBO&to=MBA&month=2026-03")
    assert page.status_code == 200
    assert b"March 2026" in page.data
    assert b"depart=2026-03-05" in page.data
    assert b"heat-" in page.data


def test_fare_calendar_ignores_bad_month(client):
    assert client.get("/search/calendar?month=nonsense").status_code == 200


def test_fare_calendar_has_no_prices_in_the_past(seeded):
    result = search.fare_calendar("NBO", "MBA", date(2026, 3, 1), "Economy", TODAY)
    first_day = result.weeks[0][-1]
    assert first_day.day == date(2026, 3, 1)
    assert first_day.price is None
    assert first_day.in_past is True
    assert result.cheapest <= result.dearest


def test_calendar_month_navigation_wraps_years():
    fare_calendar = search.FareCalendar(date(2026, 12, 1), [], None, None)
    assert fare_calendar.next_month == date(2027, 1, 1)
    assert fare_calendar.previous_month == date(2026, 11, 1)


@pytest.mark.parametrize(("price", "level"), [(100, 0), (150, 3), (199, 5), (200, 5)])
def test_heat_levels(price, level):
    assert search.heat_level(price, 100, 200) == level


def test_heat_level_handles_flat_month():
    assert search.heat_level(100, 100, 100) == 0


def test_home_shows_live_destinations_deals_and_map(client):
    page = client.get("/")
    assert page.status_code == 200
    assert b"Mombasa" in page.data
    assert b"KSh" in page.data
    assert b"map-route" in page.data


def test_deals_are_sorted_cheapest_first(seeded):
    deals = search.lowest_fares(clock.today())
    prices = [deal["price"] for deal in deals]
    assert prices == sorted(prices)
    assert 0 < len(deals) <= 6


def test_map_projection_stays_in_bounds(seeded):
    network = search.route_map(TODAY)
    assert len(network["points"]) == 12
    assert all(0 <= p["x"] <= 720 and 0 <= p["y"] <= 560 for p in network["points"])
    assert any(p["is_hub"] for p in network["points"])


def test_map_prices_each_route_by_its_own_fare(seeded):
    routes = {(r["origin"], r["destination"]): r for r in search.route_map(TODAY)["routes"]}
    assert ("NBO", "DAR") in routes
    assert ("DAR", "NBO") not in routes
    # The hub's fare to Zanzibar must not be shown for the Mombasa to Zanzibar hop.
    assert routes[("MBA", "ZNZ")]["price"] == 9000
    assert routes[("NBO", "ZNZ")]["price"] >= 17500


def test_airports_api_powers_autocomplete(client):
    payload = client.get("/api/v1/airports").get_json()
    assert payload["ok"] is True
    assert {"NBO", "ZNZ"} <= {airport["code"] for airport in payload["data"]}


def test_validate_filters_ignores_bad_values():
    assert validators.validate_filters({"sort": "x", "time": "y", "max_price": "z"}) == {
        "sort": "price",
        "time": "",
        "max_price": None,
    }
