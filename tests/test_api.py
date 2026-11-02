"""The public JSON API: shapes, validation errors and rate limiting."""

from __future__ import annotations

from anga import create_app
from tests.helpers import TODAY, future_date

FLIGHTS = f"/api/v1/flights?from=NBO&to=MBA&date={future_date()}"


def errors_of(response):
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == 400
    return payload["error"]["fields"]


def test_airports_shape(client):
    payload = client.get("/api/v1/airports").get_json()
    assert payload["ok"] is True
    assert payload["meta"]["count"] == 12
    assert set(payload["data"][0]) == {"code", "city", "name", "country", "timezone", "lat", "lng"}


def test_flights_shape(client):
    payload = client.get(FLIGHTS).get_json()
    assert payload["ok"] is True
    assert payload["meta"]["cabin"] == "Economy"
    flight = payload["data"][0]
    assert flight["flight_number"] in ("AN101", "AN103")
    assert {"Lite", "Classic", "Flex"} == {fare["fare_family"] for fare in flight["fares"]}
    fare = flight["fares"][0]
    assert isinstance(fare["price"], int)
    assert fare["currency"] == "KES"


def test_flights_cabin_filter(client):
    data = client.get(f"{FLIGHTS}&cabin=Business").get_json()["data"]
    assert {fare["cabin"] for flight in data for fare in flight["fares"]} == {"Business"}


def test_flights_validation(client):
    fields = errors_of(client.get("/api/v1/flights"))
    assert {"from", "to", "date"} <= set(fields)
    assert (
        "Unknown"
        in errors_of(client.get(f"/api/v1/flights?from=XXX&to=MBA&date={future_date()}"))["from"]
    )
    assert "cabin" in errors_of(client.get(f"{FLIGHTS}&cabin=Cargo"))
    assert (
        "past" in errors_of(client.get("/api/v1/flights?from=NBO&to=MBA&date=2020-01-01"))["date"]
    )
    assert (
        "different"
        in errors_of(client.get(f"/api/v1/flights?from=NBO&to=NBO&date={future_date()}"))["to"]
    )


def test_status_shape_and_default_date(client):
    payload = client.get("/api/v1/flights/an101/status").get_json()
    assert payload["data"]["flight_number"] == "AN101"
    assert payload["data"]["date"] == TODAY.isoformat()
    assert {"status", "delay_minutes", "gate", "estimated_departure", "progress"} <= set(
        payload["data"]
    )


def test_status_errors(client):
    assert "number" in errors_of(client.get("/api/v1/flights/BOGUS/status"))
    assert "date" in errors_of(client.get("/api/v1/flights/AN101/status?date=soon"))
    missing = client.get("/api/v1/flights/AN999/status")
    assert missing.status_code == 404
    assert missing.get_json()["ok"] is False


def test_fare_calendar_shape(client):
    payload = client.get("/api/v1/fare-calendar?from=NBO&to=MBA&month=2026-03").get_json()
    assert payload["meta"]["month"] == "2026-03"
    assert payload["meta"]["cheapest"] <= payload["meta"]["dearest"]
    assert {"date", "price", "currency", "heat"} == set(payload["data"][0])
    assert all(day["date"] >= TODAY.isoformat() for day in payload["data"])


def test_fare_calendar_validation(client):
    fields = errors_of(client.get("/api/v1/fare-calendar?from=NBO&to=MBA&month=March"))
    assert "month" in fields


def test_board_shape(client):
    payload = client.get("/api/v1/board/nbo?type=arrivals").get_json()
    assert payload["meta"] == {
        "airport": "NBO",
        "type": "arrivals",
        "date": TODAY.isoformat(),
        "count": len(payload["data"]),
    }
    assert all(row["destination"] == "NBO" for row in payload["data"])


def test_board_errors(client):
    assert "type" in errors_of(client.get("/api/v1/board/NBO?type=sideways"))
    assert client.get("/api/v1/board/XXX").status_code == 404


def test_unknown_api_route_returns_json_not_html(client):
    response = client.get("/api/v1/nothing")
    assert response.status_code == 404
    assert response.get_json()["ok"] is False


def test_wrong_method_returns_json(client):
    response = client.post("/api/v1/airports")
    assert response.status_code == 405
    assert response.get_json()["error"]["code"] == 405


def test_cors_is_off_by_default(client):
    response = client.get("/api/v1/airports", headers={"Origin": "https://elsewhere.example"})
    assert "Access-Control-Allow-Origin" not in response.headers


def test_rate_limit_returns_429_with_retry_after(tmp_path, seeded_template):
    import shutil

    path = tmp_path / "limited.db"
    shutil.copyfile(seeded_template, path)
    app = create_app(
        "testing", {"DATABASE_PATH": str(path), "API_RATE_PER_MINUTE": 1, "API_RATE_BURST": 2}
    )
    client = app.test_client()
    assert client.get("/api/v1/airports").status_code == 200
    assert client.get("/api/v1/airports").status_code == 200
    limited = client.get("/api/v1/airports")
    assert limited.status_code == 429
    assert limited.headers["Retry-After"]
    assert limited.get_json()["error"]["code"] == 429
    # The rest of the site is unaffected.
    assert client.get("/about").status_code == 200
