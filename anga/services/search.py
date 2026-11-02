"""Flight search, the fare calendar and the fare-driven parts of the home page."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from sqlite3 import Row

from anga.repositories import airports as airports_repo
from anga.repositories import fares as fares_repo
from anga.repositories import flights as flights_repo
from anga.services import pricing

LOW_SEATS_THRESHOLD = 5
TIME_WINDOWS = {
    "morning": ("00:00", "11:59"),
    "afternoon": ("12:00", "16:59"),
    "evening": ("17:00", "23:59"),
}
HEAT_LEVELS = 6
HUB = "NBO"


@dataclass
class FareOption:
    id: int
    cabin: str
    family: str
    price: int
    seats_left: int
    rules: pricing.FamilyRules

    @property
    def low_stock(self) -> bool:
        return 0 < self.seats_left <= LOW_SEATS_THRESHOLD


@dataclass
class FlightOption:
    flight: Row
    fares: list[FareOption] = field(default_factory=list)

    @property
    def cheapest(self) -> int | None:
        prices = [fare.price for fare in self.fares if fare.seats_left > 0]
        return min(prices) if prices else None

    @property
    def is_sold_out(self) -> bool:
        return self.cheapest is None


def live_price(fare: Row, day: date) -> int:
    """Today's price for a fare row, applying weekend and demand adjustments."""
    load = pricing.load_factor(fare["cabin_total"], fare["cabin_available"])
    return pricing.dynamic_price(fare["price"], day, load)


def flight_option(flight: Row, cabin: str | None, seats_needed: int) -> FlightOption:
    """A flight with the fares that can actually seat this party."""
    day = date.fromisoformat(flight["departure_date"])
    option = FlightOption(flight)
    for fare in fares_repo.for_flight(flight["id"]):
        if cabin and fare["cabin"] != cabin:
            continue
        seats_left = fare["available_seats"]
        option.fares.append(
            FareOption(
                id=fare["id"],
                cabin=fare["cabin"],
                family=fare["fare_family"],
                price=live_price(fare, day),
                seats_left=seats_left if seats_left >= seats_needed else 0,
                rules=pricing.FARE_RULES[fare["fare_family"]],
            )
        )
    return option


def search_flights(
    origin: str,
    destination: str,
    day: date,
    cabin: str,
    seats_needed: int,
    sort: str = "price",
    time_of_day: str = "",
    max_price: int | None = None,
) -> list[FlightOption]:
    """Flights on a route and date, filtered and sorted for the results page."""
    options = [
        flight_option(flight, cabin, seats_needed)
        for flight in flights_repo.find(origin, destination, day.isoformat())
    ]
    options = [option for option in options if option.fares]
    if time_of_day:
        start, end = TIME_WINDOWS[time_of_day]
        options = [o for o in options if start <= o.flight["departure_time"] <= end]
    if max_price:
        options = [o for o in options if o.cheapest is not None and o.cheapest <= max_price]
    return _sorted_options(options, sort)


def _sorted_options(options: list[FlightOption], sort: str) -> list[FlightOption]:
    keys = {
        "price": lambda o: (o.cheapest is None, o.cheapest or 0),
        "departure": lambda o: o.flight["departure_time"],
        "duration": lambda o: o.flight["duration_minutes"],
    }
    return sorted(options, key=keys.get(sort, keys["price"]))


def cheapest_on(origin: str, destination: str, day: date, cabin: str) -> int | None:
    rows = fares_repo.in_date_range(origin, destination, day.isoformat(), day.isoformat(), cabin)
    return min((live_price(row, day) for row in rows), default=None)


def nearby_dates(
    origin: str, destination: str, day: date, cabin: str, today: date, spread: int = 3
) -> list[dict]:
    """Cheapest fares on the days around ``day``, for the empty results state."""
    start = max(today, day - timedelta(days=spread))
    end = day + timedelta(days=spread)
    return [
        day_cell
        for day_cell in _cheapest_by_day(origin, destination, start, end, cabin)
        if day_cell["date"] != day
    ]


def _cheapest_by_day(
    origin: str, destination: str, start: date, end: date, cabin: str
) -> list[dict]:
    rows = fares_repo.in_date_range(origin, destination, start.isoformat(), end.isoformat(), cabin)
    best: dict[str, int] = {}
    for row in rows:
        day = row["departure_date"]
        price = live_price(row, date.fromisoformat(day))
        best[day] = min(price, best.get(day, price))
    return [{"date": date.fromisoformat(day), "price": best[day]} for day in sorted(best)]


@dataclass
class CalendarDay:
    day: date
    price: int | None = None
    heat: int = 0
    in_past: bool = False


@dataclass
class FareCalendar:
    month: date
    weeks: list[list[CalendarDay | None]]
    cheapest: int | None
    dearest: int | None

    @property
    def previous_month(self) -> date:
        return (self.month - timedelta(days=1)).replace(day=1)

    @property
    def next_month(self) -> date:
        return (self.month + timedelta(days=32)).replace(day=1)


def heat_level(price: int, cheapest: int, dearest: int) -> int:
    """Position of a price between the month's extremes, from 0 (cheap) to 5."""
    if dearest <= cheapest:
        return 0
    return min(HEAT_LEVELS - 1, int((price - cheapest) / (dearest - cheapest) * HEAT_LEVELS))


def fare_calendar(
    origin: str, destination: str, month: date, cabin: str, today: date
) -> FareCalendar:
    """A month grid with the cheapest fare per day, Monday first."""
    last_day = calendar.monthrange(month.year, month.month)[1]
    end = month.replace(day=last_day)
    prices = {
        cell["date"]: cell["price"]
        for cell in _cheapest_by_day(origin, destination, max(month, today), end, cabin)
    }
    cheapest = min(prices.values(), default=None)
    dearest = max(prices.values(), default=None)

    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(month.year, month.month):
        cells: list[CalendarDay | None] = []
        for number in week:
            if number == 0:
                cells.append(None)
                continue
            day = month.replace(day=number)
            price = prices.get(day)
            cells.append(
                CalendarDay(
                    day=day,
                    price=price,
                    heat=heat_level(price, cheapest, dearest) if price is not None else 0,
                    in_past=day < today,
                )
            )
        weeks.append(cells)
    return FareCalendar(month, weeks, cheapest, dearest)


def destination_fares(today: date, days: int = 30) -> list[dict]:
    """Cheapest economy fare to each destination from the hub, for the home page."""
    rows = fares_repo.economy_from_origin(
        HUB, today.isoformat(), (today + timedelta(days=days)).isoformat()
    )
    best: dict[str, dict] = {}
    for row in rows:
        price = live_price(row, date.fromisoformat(row["departure_date"]))
        current = best.get(row["destination"])
        if current is None or price < current["price"]:
            best[row["destination"]] = {
                "code": row["destination"],
                "city": row["destination_city"],
                "country": row["destination_country"],
                "price": price,
                "date": row["departure_date"],
            }
    return sorted(best.values(), key=lambda item: item["city"])


def lowest_fares(today: date, days: int = 14, limit: int = 6) -> list[dict]:
    """The fortnight's best deals: the single cheapest date for each destination."""
    deals = destination_fares(today, days)
    return sorted(deals, key=lambda item: item["price"])[:limit]


def airports() -> list[Row]:
    return airports_repo.all_airports()


# The map is a plain equirectangular projection of the network's bounding box.
MAP_WIDTH, MAP_HEIGHT = 720, 560
MAP_BOUNDS = {"west": 28.5, "east": 42.5, "north": 2.0, "south": -8.5}


def project(lat: float, lng: float) -> tuple[float, float]:
    x = (lng - MAP_BOUNDS["west"]) / (MAP_BOUNDS["east"] - MAP_BOUNDS["west"]) * MAP_WIDTH
    y = (MAP_BOUNDS["north"] - lat) / (MAP_BOUNDS["north"] - MAP_BOUNDS["south"]) * MAP_HEIGHT
    return round(x, 1), round(y, 1)


def route_map(today: date) -> dict:
    """Airports and routes laid out for the home page's SVG map."""
    prices = {item["code"]: item["price"] for item in destination_fares(today)}
    points = []
    for airport in airports():
        x, y = project(airport["lat"], airport["lng"])
        points.append(
            {"code": airport["code"], "city": airport["city"], "x": x, "y": y,
             "is_hub": airport["code"] == HUB, "price": prices.get(airport["code"])}
        )  # fmt: skip

    routes = []
    seen = set()
    for route in flights_repo.distinct_routes():
        pair = tuple(sorted((route["origin"], route["destination"])))
        if pair in seen:
            continue
        seen.add(pair)
        x1, y1 = project(route["origin_lat"], route["origin_lng"])
        x2, y2 = project(route["destination_lat"], route["destination_lng"])
        bend = 0.16 * ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        routes.append(
            {
                "origin": route["origin"],
                "destination": route["destination"],
                "origin_city": route["origin_city"],
                "destination_city": route["destination_city"],
                "path": (
                    f"M{x1} {y1} Q{round((x1 + x2) / 2, 1)} "
                    f"{round((y1 + y2) / 2 - bend, 1)} {x2} {y2}"
                ),
                "price": prices.get(route["destination"], route["base_fare"]),
            }
        )
    return {"width": MAP_WIDTH, "height": MAP_HEIGHT, "points": points, "routes": routes}
