"""Dashboard figures and chart geometry.

Charts are drawn server-side as SVG with no library. Geometry is computed here
as plain data, so the arithmetic is testable and templates only draw shapes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from anga import clock
from anga.repositories import analytics as analytics_repo
from anga.repositories import audit as audit_repo
from anga.services import pricing
from anga.templating import format_ksh

CHART_WIDTH = 640
CHART_HEIGHT = 240
PAD_LEFT = 62
PAD_RIGHT = 12
PAD_TOP = 12
PAD_BOTTOM = 26
AXIS_TICKS = 4


def _day_start(day: date) -> str:
    return datetime.combine(day, datetime.min.time()).isoformat(timespec="seconds")


def nice_ceiling(value: int) -> int:
    """Round a maximum up to a tidy axis value such as 40,000 or 150,000."""
    if value <= 0:
        return 1000
    magnitude = 10 ** (len(str(value)) - 1)
    for step in (1, 1.5, 2, 3, 4, 5, 7.5, 10):
        if value <= step * magnitude:
            return int(step * magnitude)
    return 10 * magnitude


@dataclass
class LineChart:
    path: str
    area: str
    points: list[dict]
    ticks: list[dict]
    labels: list[dict]
    width: int = CHART_WIDTH
    height: int = CHART_HEIGHT
    left: int = PAD_LEFT
    right: int = CHART_WIDTH - PAD_RIGHT
    baseline: int = CHART_HEIGHT - PAD_BOTTOM


def line_chart(series: list[tuple[date, int]]) -> LineChart:
    """Lay a daily series out on the chart's single axis.

    The axis starts at zero, and allows for days where refunds exceed sales.
    """
    plot_width = CHART_WIDTH - PAD_LEFT - PAD_RIGHT
    plot_height = CHART_HEIGHT - PAD_TOP - PAD_BOTTOM
    top = nice_ceiling(max((value for _, value in series), default=0))
    bottom = CHART_HEIGHT - PAD_BOTTOM
    step = plot_width / max(len(series) - 1, 1)

    points = []
    for index, (day, value) in enumerate(series):
        clamped = max(0, value)
        points.append(
            {
                "x": round(PAD_LEFT + index * step, 1),
                "y": round(bottom - clamped / top * plot_height, 1),
                "day": day,
                "value": value,
                "label": f"{day:%a %d %b}: {format_ksh(value)}",
                "hit_x": round(PAD_LEFT + index * step - step / 2, 1),
                "hit_width": round(step, 1),
            }
        )
    path = "M" + " L".join(f"{p['x']} {p['y']}" for p in points) if points else ""
    area = f"{path} L{points[-1]['x']} {bottom} L{points[0]['x']} {bottom}Z" if points else ""
    ticks = [
        {
            "y": round(bottom - plot_height * i / AXIS_TICKS, 1),
            "label": f"{round(top * i / AXIS_TICKS):,}",
        }
        for i in range(AXIS_TICKS + 1)
    ]
    labels = [
        {"x": p["x"], "text": f"{p['day']:%d %b}"}
        for i, p in enumerate(points)
        if i % max(len(points) // 5, 1) == 0
    ]
    return LineChart(path, area, points, ticks, labels)


def bar_rows(rows: list, value_key: str) -> list[dict]:
    """Horizontal bars as a percentage of the largest value."""
    largest = max((row[value_key] for row in rows), default=0) or 1
    return [
        {
            "label": f"{row['origin']} → {row['destination']}",
            "value": row[value_key],
            "width": round(row[value_key] / largest * 100, 1),
        }
        for row in rows
    ]


CABIN_ORDER = ("Economy", "Business", "First")


def stacked_segments(rows: list) -> list[dict]:
    """One stacked bar, in fixed cabin order so colours follow the cabin, never its rank."""
    counts = {row["cabin"]: row["passengers"] for row in rows}
    total = sum(counts.values()) or 1
    segments = []
    offset = 0.0
    for cabin in CABIN_ORDER:
        count = counts.get(cabin, 0)
        share = count / total * 100
        segments.append(
            {
                "cabin": cabin,
                "count": count,
                "share": round(share, 1),
                "x": round(offset, 2),
                "width": round(share, 2),
            }
        )
        offset += share
    return segments


def dashboard(today: date | None = None) -> dict:
    today = today or clock.today()
    tomorrow = _day_start(today + timedelta(days=1))
    day_ago = {n: _day_start(today - timedelta(days=n)) for n in (0, 6, 29)}

    daily = analytics_repo.revenue_by_day(day_ago[29], tomorrow)
    series = [
        (today - timedelta(days=offset), daily.get((today - timedelta(days=offset)).isoformat(), 0))
        for offset in range(29, -1, -1)
    ]
    load = analytics_repo.load_between(today.isoformat(), (today + timedelta(days=6)).isoformat())
    pending = analytics_repo.pending_payments()
    departures = [
        {
            **dict(row),
            "load": round(pricing.load_factor(row["total"], row["available"]) * 100),
        }
        for row in analytics_repo.departures_with_load(today.isoformat())
    ]
    return {
        "revenue_today": analytics_repo.revenue_since(day_ago[0], tomorrow),
        "revenue_7": analytics_repo.revenue_since(day_ago[6], tomorrow),
        "revenue_30": analytics_repo.revenue_since(day_ago[29], tomorrow),
        "bookings_7": analytics_repo.bookings_since(day_ago[6]),
        "load_factor": round(pricing.load_factor(load["total"], load["available"]) * 100),
        "pending_count": pending["count"],
        "pending_amount": pending["amount"],
        "revenue_chart": line_chart(series),
        "revenue_table": series,
        "top_routes": bar_rows(analytics_repo.top_routes(day_ago[29], 6), "revenue"),
        "cabin_mix": stacked_segments(analytics_repo.cabin_mix(day_ago[29])),
        "departures": departures,
        "activity": audit_repo.search(None, None, 8)[0],
    }
