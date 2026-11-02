"""The operations console: permissions, flights, bookings, promos and audit."""

from __future__ import annotations

import pytest

from anga import db
from anga.services import analytics
from tests.helpers import TODAY

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
