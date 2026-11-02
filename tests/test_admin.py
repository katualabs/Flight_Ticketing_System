"""The operations console: permissions, flights, bookings, promos and audit."""

from __future__ import annotations

import pytest

from anga import db
from anga.services import analytics, ops
from tests.helpers import TODAY, future_date, get_flight

STAFF = {
    "admin": ("admin@anga.example", "AngaAdmin#2026"),
    "agent": ("agent@anga.example", "AngaAgent#2026"),
    "customer": ("wanjiru@anga.example", "AngaFly#2026"),
}


@pytest.fixture
def admin(client):
    email, password = STAFF["admin"]
    client.post("/account/login", data={"email": email, "password": password})
    return client


@pytest.fixture
def agent(client):
    email, password = STAFF["agent"]
    client.post("/account/login", data={"email": email, "password": password})
    return client


def audit_actions(app):
    with app.app_context():
        return [r["action"] for r in db.fetch_all("SELECT action FROM audit_log")]


def test_anonymous_visitors_are_sent_to_login(client):
    response = client.get("/admin/")
    assert response.status_code == 302
    assert "/account/login" in response.headers["Location"]


def test_customers_get_403(client):
    email, password = STAFF["customer"]
    client.post("/account/login", data={"email": email, "password": password})
    assert client.get("/admin/").status_code == 403


def test_admin_pages_are_not_cached(admin):
    assert admin.get("/admin/").headers["Cache-Control"] == "no-store"


def test_dashboard_shows_kpis_charts_and_departures(admin):
    page = admin.get("/admin/")
    assert page.status_code == 200
    for fragment in (b"Revenue today", b"Load factor", b"Pending payments", b"chart-line"):
        assert fragment in page.data
    assert b"Top routes" in page.data
    assert b"Cabin mix" in page.data
    assert b"View as a table" in page.data
    assert b"<meter" in page.data


def test_nav_only_offers_what_the_role_can_use(agent):
    page = agent.get("/admin/").data
    assert b">Promo codes<" not in page
    assert b">Settings<" not in page


def test_dashboard_figures_agree_with_payments(seeded):
    figures = analytics.dashboard(TODAY)
    net = db.fetch_value(
        "SELECT COALESCE(SUM(CASE kind WHEN 'charge' THEN amount ELSE -amount END), 0)"
        " FROM payments WHERE status = 'succeeded' AND created_at >= ?",
        (f"{TODAY.isoformat()}T00:00:00",),
    )
    assert figures["revenue_today"] == net
    assert figures["revenue_30"] >= figures["revenue_7"] >= figures["revenue_today"] >= 0
    assert sum(value for _, value in figures["revenue_table"]) == figures["revenue_30"]
    assert 0 <= figures["load_factor"] <= 100


def test_line_chart_geometry_starts_at_zero_and_fits_the_plot():
    series = [(TODAY, 0), (TODAY, 50_000), (TODAY, 100_000)]
    chart = analytics.line_chart(series)
    assert chart.points[0]["y"] == chart.baseline
    assert chart.points[-1]["y"] < chart.baseline
    assert all(chart.left <= p["x"] <= chart.right for p in chart.points)
    assert chart.ticks[0]["label"] == "0"
    assert chart.path.startswith("M")


def test_line_chart_copes_with_no_data_and_refund_days():
    assert analytics.line_chart([]).path == ""
    chart = analytics.line_chart([(TODAY, -500), (TODAY, 0)])
    assert chart.points[0]["y"] == chart.baseline


@pytest.mark.parametrize(
    ("value", "ceiling"),
    [(0, 1000), (950, 1000), (1100, 1500), (41_000, 50_000), (99_000, 100_000)],
)
def test_axis_ceilings_are_tidy(value, ceiling):
    assert analytics.nice_ceiling(value) == ceiling


def test_stacked_segments_keep_fixed_order_and_add_up():
    rows = [{"cabin": "First", "passengers": 1}, {"cabin": "Economy", "passengers": 3}]
    segments = analytics.stacked_segments(rows)
    assert [s["cabin"] for s in segments] == ["Economy", "Business", "First"]
    assert sum(s["share"] for s in segments) == 100
    assert segments[2]["x"] == 75


def test_bar_rows_scale_to_the_largest():
    rows = [
        {"origin": "NBO", "destination": "MBA", "revenue": 100},
        {"origin": "NBO", "destination": "KIS", "revenue": 50},
    ]
    assert [row["width"] for row in analytics.bar_rows(rows, "revenue")] == [100, 50]


ADMIN_ONLY = [
    "/admin/flights/new",
    "/admin/flights/generate",
]


@pytest.mark.parametrize("path", ADMIN_ONLY)
def test_agents_cannot_reach_flight_editing(agent, path):
    assert agent.get(path).status_code == 403


def test_agent_cannot_change_prices_or_delete(agent, app):
    with app.app_context():
        flight = get_flight()
        fare = ops.fares_for(flight["id"])[0]
    url = f"/admin/flights/{flight['id']}"
    assert agent.get(url).status_code == 200
    assert agent.post(f"{url}/fares/{fare['id']}", data={"price": 1}).status_code == 403
    assert agent.post(f"{url}/delete").status_code == 403
    assert agent.post(f"{url}/cancel").status_code == 403
    assert agent.post(f"{url}/times", data={}).status_code == 403
    assert b"Price (KSh)" not in agent.get(url).data


def test_flight_list_filters_and_paginates(admin):
    page = admin.get("/admin/flights")
    assert b"Page 1 of" in page.data
    filtered = admin.get(f"/admin/flights?q=AN101&date={future_date()}")
    assert b"AN101" in filtered.data
    assert b"AN201" not in filtered.data
    assert b"Page 2" in admin.get("/admin/flights?page=2").data


FLIGHT_FORM = {
    "flight_number": "AN901",
    "origin": "NBO",
    "destination": "MBA",
    "departure_date": future_date(),
    "departure_time": "22:00",
    "duration_minutes": "75",
    "aircraft_code": "E190",
    "base_fare": "7000",
}


def test_create_flight_with_fares_and_seats(admin, app):
    assert admin.get("/admin/flights/new").status_code == 200
    response = admin.post("/admin/flights/new", data=FLIGHT_FORM)
    assert response.status_code == 302
    with app.app_context():
        flight = get_flight("AN901")
        assert flight["arrival_time"] == "23:15"
        assert len(ops.fares_for(flight["id"])) == 6
        assert (
            db.fetch_value("SELECT COUNT(*) FROM seats WHERE flight_id = ?", (flight["id"],)) > 50
        )
    assert "flight.create" in audit_actions(app)


def test_new_flight_shows_up_in_public_search(admin):
    admin.post("/admin/flights/new", data=FLIGHT_FORM)
    page = admin.get(f"/search/?from=NBO&to=MBA&depart={future_date()}&trip=one_way&adults=1")
    assert b"AN901" in page.data


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("flight_number", "XX1", b"look like AN101"),
        ("destination", "NBO", b"different destination"),
        ("departure_date", "2020-01-01", b"from today"),
        ("departure_time", "99:99", b"HH:MM"),
        ("duration_minutes", "0", b"duration"),
        ("base_fare", "0", b"base fare"),
    ],
)
def test_flight_form_validation(admin, field, value, fragment):
    page = admin.post("/admin/flights/new", data={**FLIGHT_FORM, field: value})
    assert page.status_code == 400
    assert fragment in page.data


def test_duplicate_flight_is_refused(admin):
    admin.post("/admin/flights/new", data=FLIGHT_FORM)
    page = admin.post("/admin/flights/new", data=FLIGHT_FORM)
    assert page.status_code == 400
    assert b"already flies" in page.data


def test_bad_airport_and_aircraft_are_refused(admin):
    assert (
        b"valid airports"
        in admin.post("/admin/flights/new", data={**FLIGHT_FORM, "origin": "XXX"}).data
    )
    assert (
        b"valid aircraft"
        in admin.post("/admin/flights/new", data={**FLIGHT_FORM, "aircraft_code": "A380"}).data
    )


def test_update_times_recalculates_arrival(admin, app):
    with app.app_context():
        flight = get_flight()
    url = f"/admin/flights/{flight['id']}/times"
    admin.post(url, data={"departure_time": "09:00", "duration_minutes": "90"})
    with app.app_context():
        assert get_flight()["arrival_time"] == "10:30"
    page = admin.post(
        url, data={"departure_time": "x", "duration_minutes": "0"}, follow_redirects=True
    )
    assert b"valid departure time" in page.data


def test_fare_editor_changes_price_and_guards_sold_seats(admin, app):
    with app.app_context():
        flight = get_flight()
        fare = ops.fares_for(flight["id"])[0]
    url = f"/admin/flights/{flight['id']}/fares/{fare['id']}"
    sold = fare["total_seats"] - fare["available_seats"]
    ok = admin.post(
        url,
        data={
            "price": "5000",
            "total_seats": fare["total_seats"],
            "available_seats": fare["available_seats"],
        },
        follow_redirects=True,
    )
    assert b"updated" in ok.data
    with app.app_context():
        assert ops.get_fare(fare["id"])["price"] == 5000
    if sold:
        shrunk = admin.post(
            url,
            data={"price": "5000", "total_seats": sold - 1, "available_seats": 0},
            follow_redirects=True,
        )
        assert b"already sold" in shrunk.data
    over = admin.post(
        url,
        data={
            "price": "5000",
            "total_seats": fare["total_seats"],
            "available_seats": fare["total_seats"] + 1,
        },
        follow_redirects=True,
    )
    assert b"cannot exceed" in over.data
    oversold = admin.post(
        url,
        data={"price": "5000", "total_seats": "999", "available_seats": fare["available_seats"]},
        follow_redirects=True,
    )
    assert b"physical seats" in oversold.data
    bad = admin.post(url, data={"price": "-1"}, follow_redirects=True)
    assert b"price in shillings" in bad.data
    assert "fare.update" in audit_actions(app)


def test_fare_of_another_flight_is_404(admin, app):
    with app.app_context():
        flight = get_flight()
        other = ops.fares_for(get_flight("AN103")["id"])[0]
    assert admin.post(f"/admin/flights/{flight['id']}/fares/{other['id']}").status_code == 404


def test_delete_only_without_bookings(admin, app):
    from anga.services import booking as booking_service

    with app.app_context():
        booked = booking_service.get_by_reference("ANDEMO01")
        flight_id = booking_service.bookings_repo.segments(booked["id"])[0]["flight_id"]
        empty = get_flight("AN301", 15)["id"]
    refused = admin.post(f"/admin/flights/{flight_id}/delete", follow_redirects=True)
    assert b"Cancel it instead" in refused.data
    with app.app_context():
        assert ops.get_flight(flight_id) is not None
    assert admin.post(f"/admin/flights/{empty}/delete").status_code == 302
    with app.app_context():
        assert ops.get_flight(empty) is None
    assert "flight.delete" in audit_actions(app)


def test_cancel_flight_notifies_and_marks_for_rebooking(admin, app):
    from anga.repositories import outbox
    from anga.services import booking as booking_service

    with app.app_context():
        booked = booking_service.get_by_reference("ANDEMO01")
        flight_id = booking_service.bookings_repo.segments(booked["id"])[0]["flight_id"]
    page = admin.post(f"/admin/flights/{flight_id}/cancel", follow_redirects=True)
    assert b"marked for rebooking" in page.data
    with app.app_context():
        assert booking_service.get_by_reference("ANDEMO01")["needs_rebooking"] == 1
        assert "cancelled" in outbox.for_recipient("wanjiru@anga.example")[0]["subject"]


def test_cancelled_flight_can_be_rebooked_free_then_clears_the_flag(admin, app):
    from anga.services import booking as booking_service
    from anga.services import manage

    with app.app_context():
        booked = booking_service.get_by_reference("ANDEMO01")
        segment = booking_service.bookings_repo.segments(booked["id"])[0]
    admin.post(f"/admin/flights/{segment['flight_id']}/cancel")
    with app.app_context():
        booked = booking_service.get_by_reference("ANDEMO01")
        target = get_flight("AN103", 2)
        assert manage.change_flight(booked, segment["segment_id"], target["id"]) == 0
        assert booking_service.get_by_reference("ANDEMO01")["needs_rebooking"] == 0


def test_cancelling_a_rebook_booking_refunds_in_full(admin, app):
    from anga.services import booking as booking_service
    from anga.services import manage

    with app.app_context():
        booked = booking_service.get_by_reference("ANDEMO01")
        segment = booking_service.bookings_repo.segments(booked["id"])[0]
    admin.post(f"/admin/flights/{segment['flight_id']}/cancel")
    with app.app_context():
        booked = booking_service.get_by_reference("ANDEMO01")
        assert manage.cancellation_quote(booked).refund == booked["total"]


def test_departed_flight_cannot_be_cancelled(admin, app):
    with app.app_context():
        flight = get_flight()
        db.execute("UPDATE flights SET status = 'Departed' WHERE id = ?", (flight["id"],))
    page = admin.post(f"/admin/flights/{flight['id']}/cancel", follow_redirects=True)
    assert b"cannot be cancelled" in page.data


def test_bulk_schedule_generation(admin, app):
    assert b"Generate flights" in admin.get("/admin/flights/generate").data
    page = admin.post(
        "/admin/flights/generate",
        data={
            "flight_number": "AN321",
            "start": "2026-04-06",
            "end": "2026-04-19",
            "weekdays": ["1", "3"],
        },
        follow_redirects=True,
    )
    assert b"4 flight(s) created, 0 already existed" in page.data
    with app.app_context():
        dates = [
            row[0]
            for row in db.fetch_all(
                "SELECT departure_date FROM flights WHERE flight_number = 'AN321'"
                " AND departure_date >= '2026-04-06' ORDER BY departure_date"
            )
        ]
    assert dates == ["2026-04-06", "2026-04-08", "2026-04-13", "2026-04-15"]
    again = admin.post(
        "/admin/flights/generate",
        data={
            "flight_number": "AN321",
            "start": "2026-04-06",
            "end": "2026-04-19",
            "weekdays": ["1"],
        },
        follow_redirects=True,
    )
    assert b"0 flight(s) created, 2 already existed" in again.data
    assert "flight.bulk_generate" in audit_actions(app)


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        (
            {"flight_number": "", "start": "2026-04-06", "end": "2026-04-07", "weekdays": ["1"]},
            b"Choose a route",
        ),
        (
            {
                "flight_number": "AN999",
                "start": "2026-04-06",
                "end": "2026-04-07",
                "weekdays": ["1"],
            },
            b"from the schedule",
        ),
        (
            {
                "flight_number": "AN101",
                "start": "2020-01-01",
                "end": "2026-04-07",
                "weekdays": ["1"],
            },
            b"from today",
        ),
        (
            {
                "flight_number": "AN101",
                "start": "2026-04-06",
                "end": "2026-04-01",
                "weekdays": ["1"],
            },
            b"before the start",
        ),
        (
            {
                "flight_number": "AN101",
                "start": "2026-04-06",
                "end": "2027-04-06",
                "weekdays": ["1"],
            },
            b"at most",
        ),
        (
            {"flight_number": "AN101", "start": "2026-04-06", "end": "2026-04-07"},
            b"at least one weekday",
        ),
    ],
)
def test_bulk_schedule_validation(admin, data, fragment):
    page = admin.post("/admin/flights/generate", data=data)
    assert page.status_code == 400
    assert fragment in page.data


def test_unknown_flight_is_404(admin):
    assert admin.get("/admin/flights/999999").status_code == 404


def test_status_change_is_public_at_once_and_audited(agent, app):
    with app.app_context():
        flight = get_flight(days=0)
    response = agent.post(
        f"/admin/flights/{flight['id']}/status",
        data={"status": "Delayed", "delay_minutes": "35", "gate": "c7"},
    )
    assert response.status_code == 302
    assert b"C7" in agent.get("/status/board/NBO").data
    assert "flight.status" in audit_actions(app)


def test_status_validation(agent, app):
    with app.app_context():
        flight = get_flight()
    url = f"/admin/flights/{flight['id']}/status"
    assert b"valid status" in agent.post(url, data={"status": "Lost"}, follow_redirects=True).data
    assert (
        b"Gates look like"
        in agent.post(url, data={"status": "Boarding", "gate": "Z999"}, follow_redirects=True).data
    )
    assert (
        b"Enter a delay"
        in agent.post(
            url, data={"status": "Delayed", "delay_minutes": "-1"}, follow_redirects=True
        ).data
    )


def test_setting_cancelled_status_runs_the_cancellation_rule(agent, app):
    from anga.services import booking as booking_service

    with app.app_context():
        booked = booking_service.get_by_reference("ANDEMO01")
        flight_id = booking_service.bookings_repo.segments(booked["id"])[0]["flight_id"]
    page = agent.post(
        f"/admin/flights/{flight_id}/status", data={"status": "Cancelled"}, follow_redirects=True
    )
    assert b"marked for rebooking" in page.data
    with app.app_context():
        assert booking_service.get_by_reference("ANDEMO01")["needs_rebooking"] == 1


def manifest_flight(app):
    from anga.services import booking as booking_service

    with app.app_context():
        booked = booking_service.get_by_reference("ANDEMO01")
        return booking_service.bookings_repo.segments(booked["id"])[0]["flight_id"]


def test_manifest_lists_passengers_extras_and_check_in_state(agent, app):
    flight_id = manifest_flight(app)
    page = agent.get(f"/admin/flights/{flight_id}/manifest")
    assert b"Wanjiru Kamau" in page.data
    assert b"ANDEMO01" in page.data
    assert b"Extra 23 kg bag" in page.data
    assert b"Not yet" in page.data
    assert b"KE29384756" not in page.data


def test_manifest_csv_export(agent, app):
    flight_id = manifest_flight(app)
    response = agent.get(f"/admin/flights/{flight_id}/manifest.csv")
    assert response.mimetype == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]
    body = response.get_data(as_text=True)
    assert body.splitlines()[0].startswith("seat,name,type,reference")
    assert "Wanjiru Kamau" in body
    assert "KE29384756" not in body


def test_csv_cells_cannot_inject_spreadsheet_formulas():
    body = ops.to_csv(["a"], [["=HYPERLINK(1)"], ["+1"], ["safe"]])
    assert "'=HYPERLINK(1)" in body
    assert "'+1" in body
    assert "safe" in body
