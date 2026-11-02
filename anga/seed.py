"""Demo data. Everything is generated relative to today so the demo never goes stale."""

from __future__ import annotations

import json
import os
import random
from datetime import date, datetime, time, timedelta

from flask import current_app

from anga import clock
from anga.db import get_db, init_db, transaction
from anga.repositories import airports as airports_repo
from anga.repositories import extras as extras_repo
from anga.repositories import fares as fares_repo
from anga.repositories import flights as flights_repo
from anga.repositories import promos as promos_repo
from anga.repositories import settings as settings_repo
from anga.repositories import users as users_repo
from anga.services import accounts, booking, payment, schedule

_EAT_KEN = "Africa/Nairobi"
_EAT_TZA = "Africa/Dar_es_Salaam"
AIRPORTS = [
    ("NBO", "Nairobi", "Jomo Kenyatta International", "Kenya", _EAT_KEN, -1.3192, 36.9278, 0),
    ("MBA", "Mombasa", "Moi International", "Kenya", _EAT_KEN, -4.0348, 39.5942, 1),
    ("KIS", "Kisumu", "Kisumu International", "Kenya", _EAT_KEN, -0.0861, 34.7289, 0),
    ("EDL", "Eldoret", "Eldoret International", "Kenya", _EAT_KEN, 0.4045, 35.2389, 0),
    ("MYD", "Malindi", "Malindi Airport", "Kenya", _EAT_KEN, -3.2293, 40.1017, 1),
    ("UKA", "Diani", "Ukunda Airstrip", "Kenya", _EAT_KEN, -4.2933, 39.5711, 1),
    ("LAU", "Lamu", "Manda Airport", "Kenya", _EAT_KEN, -2.2524, 40.9131, 1),
    ("ZNZ", "Zanzibar", "Abeid Amani Karume Intl", "Tanzania", _EAT_TZA, -6.2220, 39.2249, 1),
    ("DAR", "Dar es Salaam", "Julius Nyerere Intl", "Tanzania", _EAT_TZA, -6.8781, 39.2026, 1),
    ("JRO", "Kilimanjaro", "Kilimanjaro International", "Tanzania", _EAT_TZA, -3.4294, 37.0745, 0),
    ("EBB", "Entebbe", "Entebbe International", "Uganda", "Africa/Kampala", 0.0424, 32.4435, 0),
    ("KGL", "Kigali", "Kigali International", "Rwanda", "Africa/Kigali", -1.9686, 30.1395, 0),
]  # fmt: skip

_TWO_TWO = ["A", "C", "|", "D", "F"]
AIRCRAFT = {
    "B738": (
        "Boeing 737-800",
        {
            "cabins": [
                {"name": "First", "first_row": 1, "last_row": 2, "columns": _TWO_TWO},
                {"name": "Business", "first_row": 3, "last_row": 6, "columns": _TWO_TWO},
                {
                    "name": "Economy",
                    "first_row": 10,
                    "last_row": 32,
                    "skip_rows": [13],
                    "exit_rows": [18, 19],
                    "columns": ["A", "B", "C", "|", "D", "E", "F"],
                },
            ]
        },
    ),
    "E190": (
        "Embraer E190",
        {
            "cabins": [
                {"name": "Business", "first_row": 1, "last_row": 4, "columns": _TWO_TWO},
                {
                    "name": "Economy",
                    "first_row": 8,
                    "last_row": 30,
                    "skip_rows": [13],
                    "exit_rows": [15, 16],
                    "columns": _TWO_TWO,
                },
            ]
        },
    ),
    "DH8D": (
        "Dash 8-400",
        {
            "cabins": [
                {"name": "Business", "first_row": 1, "last_row": 3, "columns": _TWO_TWO},
                {
                    "name": "Economy",
                    "first_row": 5,
                    "last_row": 21,
                    "skip_rows": [13],
                    "exit_rows": [5],
                    "columns": _TWO_TWO,
                },
            ]
        },
    ),
}

ROUTES = [
    # number, from, to, departs, minutes, aircraft, base fare, weekdays (Monday = 1)
    ("AN101", "NBO", "MBA", "08:00", 75, "B738", 8500, "1234567"),
    ("AN102", "MBA", "NBO", "10:00", 75, "B738", 8500, "1234567"),
    ("AN103", "NBO", "MBA", "17:30", 75, "B738", 9200, "1234567"),
    ("AN104", "MBA", "NBO", "19:45", 75, "B738", 9200, "1234567"),
    ("AN111", "NBO", "MYD", "11:00", 80, "E190", 9000, "1234567"),
    ("AN112", "MYD", "NBO", "13:00", 80, "E190", 9000, "1234567"),
    ("AN121", "NBO", "UKA", "08:30", 85, "DH8D", 9500, "1234567"),
    ("AN122", "UKA", "NBO", "10:45", 85, "DH8D", 9500, "1234567"),
    ("AN131", "NBO", "LAU", "10:15", 95, "DH8D", 11000, "1357"),
    ("AN132", "LAU", "NBO", "12:40", 95, "DH8D", 11000, "1357"),
    ("AN141", "MBA", "ZNZ", "11:30", 60, "DH8D", 9000, "246"),
    ("AN142", "ZNZ", "MBA", "13:15", 60, "DH8D", 9000, "246"),
    ("AN201", "NBO", "KIS", "07:00", 55, "E190", 6500, "1234567"),
    ("AN202", "KIS", "NBO", "08:45", 55, "E190", 6500, "1234567"),
    ("AN211", "NBO", "EDL", "09:30", 50, "DH8D", 6000, "1234567"),
    ("AN212", "EDL", "NBO", "11:00", 50, "DH8D", 6000, "1234567"),
    ("AN301", "NBO", "ZNZ", "07:45", 95, "E190", 17500, "1234567"),
    ("AN302", "ZNZ", "NBO", "10:15", 95, "E190", 17500, "1234567"),
    ("AN311", "NBO", "DAR", "13:20", 85, "B738", 16000, "1234567"),
    ("AN312", "DAR", "NBO", "16:00", 85, "B738", 16000, "1234567"),
    ("AN321", "NBO", "JRO", "12:00", 55, "DH8D", 12500, "12345"),
    ("AN322", "JRO", "NBO", "13:40", 55, "DH8D", 12500, "12345"),
    ("AN401", "NBO", "EBB", "06:50", 75, "E190", 15000, "1234567"),
    ("AN402", "EBB", "NBO", "08:50", 75, "E190", 15000, "1234567"),
    ("AN411", "NBO", "KGL", "15:10", 90, "E190", 18500, "1234567"),
    ("AN412", "KGL", "NBO", "17:35", 90, "E190", 18500, "1234567"),
]

EXTRAS = [
    ("BAG23", "Extra 23 kg bag", 2500, "bag"),
    ("MEAL_SWAHILI", "Swahili coast meal", 950, "meal"),
    ("MEAL_VEG", "Vegetarian meal", 850, "meal"),
    ("MEAL_HALAL", "Halal meal", 850, "meal"),
    ("PRIORITY", "Priority boarding", 800, "priority"),
    ("LOUNGE", "Lounge access", 3500, "lounge"),
]

DEMO_BOOKING_COUNT = 18
DEMO_PEOPLE = [
    "Achieng Odhiambo", "Mutua Nzioka", "Fatuma Hassan", "Kiprono Rotich", "Neema Mollel",
    "Tumusiime Asiimwe", "Uwase Mukamana", "Salim Bakari", "Zawadi Mwita", "Njeri Gitau",
]  # fmt: skip

HISTORY_ROUTES = ("AN101", "AN102", "AN201", "AN202", "AN301", "AN302")
DEFAULT_SETTINGS = {
    "usd_rate": "129",
    "cancellation_hours": "3",
    "checkin_open_hours": "48",
    "checkin_close_hours": "1",
    "schedule_horizon_days": "45",
}

# Tables emptied by a reset, children before parents.
RESET_ORDER = (
    "price_watches",
    "login_attempts",
    "booking_drafts",
    "audit_log",
    "outbox",
    "contact_messages",
    "miles_ledger",
    "payments",
    "booking_extras",
    "extras",
    "passenger_seats",
    "seats",
    "booking_passengers",
    "booking_segments",
    "bookings",
    "promo_codes",
    "saved_travellers",
    "users",
    "fares",
    "flights",
    "route_schedules",
    "aircraft_types",
    "airports",
    "settings",
)


def is_seeded() -> bool:
    return settings_repo.get("seeded_at") is not None


def reset() -> None:
    """Empty every table while keeping the schema."""
    with transaction() as conn:
        for table in RESET_ORDER:
            conn.execute(f"DELETE FROM {table}")  # noqa: S608 - constant table names


def seed_reference_data() -> None:
    with transaction():
        airports_repo.insert_many(AIRPORTS)
        airports_repo.insert_aircraft(
            (code, name, json.dumps(layout)) for code, (name, layout) in AIRCRAFT.items()
        )
        flights_repo.insert_route_templates(ROUTES)
        extras_repo.insert_many(EXTRAS)
        for key, value in DEFAULT_SETTINGS.items():
            settings_repo.put(key, value)


def seed_promos() -> None:
    today = clock.today()
    start = (today - timedelta(days=30)).isoformat()
    end = (today + timedelta(days=365)).isoformat()
    with transaction():
        promos_repo.insert("KARIBU10", "percent", 10, "all", 10000, start, end, None)
        promos_repo.insert("COAST2026", "fixed", 1500, "coastal", 0, start, end, 500)
        promos_repo.insert(
            "EXPIRED5",
            "percent",
            5,
            "all",
            0,
            (today - timedelta(days=120)).isoformat(),
            (today - timedelta(days=30)).isoformat(),
            None,
        )


def seed_users() -> dict[str, int]:
    """Demo accounts. Every person and address here is fictional."""
    env = os.environ.get
    with transaction():
        return {
            "admin": accounts.create_user(
                "Amani Mwangi",
                "admin@anga.example",
                "+254700000001",
                env("ANGA_ADMIN_PASSWORD", "AngaAdmin#2026"),
                "admin",
            ),
            "agent": accounts.create_user(
                "Baraka Otieno",
                "agent@anga.example",
                "+254700000002",
                env("ANGA_AGENT_PASSWORD", "AngaAgent#2026"),
                "agent",
            ),
            "customer": accounts.create_user(
                "Wanjiru Kamau",
                "wanjiru@anga.example",
                "+254700000003",
                env("ANGA_CUSTOMER_PASSWORD", "AngaFly#2026"),
                "customer",
            ),
        }


def _demo_draft(
    fare_refs: list[tuple[str, date, str, str]],
    people: list[tuple[str, str]],
    email: str,
    phone: str,
    extras: dict | None = None,
) -> dict | None:
    """Build a draft for specific flights; None if that flight does not run that day."""
    fares = []
    for number, day, cabin, family in fare_refs:
        flight = flights_repo.get_by_number(number, day.isoformat())
        if flight is None:
            return None
        fares.append(fares_repo.get(flight["id"], cabin, family))
    if any(fare is None or fare["available_seats"] < len(people) for fare in fares):
        return None
    draft = booking.new_draft(
        fares[0]["id"], fares[1]["id"] if len(fares) > 1 else None, len(people), 0, 0
    )
    draft["passengers"] = [
        {"full_name": name, "id_number": id_number, "date_of_birth": None}
        for name, id_number in people
    ]
    draft["contact"] = {"email": email, "phone": phone}
    draft["extras"] = extras or {}
    return draft


def seed_demo_bookings(users: dict[str, int]) -> None:
    """Demo bookings made through the real services, so all the numbers agree.

    Past bookings are made by moving the clock back, so they go through exactly
    the same checks, payments, miles and emails as a customer's booking today.
    """
    now = clock.now()
    today = now.date()
    wanjiru = users["customer"]
    her_party = [("Wanjiru Kamau", "KE29384756"), ("Daudi Kamau", "KE10293847")]

    # Check-in is open for this one: it departs tomorrow, whenever "today" is.
    draft = _demo_draft(
        [
            ("AN101", today + timedelta(days=1), "Economy", "Classic"),
            ("AN102", today + timedelta(days=6), "Economy", "Classic"),
        ],
        her_party,
        "wanjiru@anga.example",
        "+254700000003",
        {"0": {"BAG23": 1, "MEAL_SWAHILI": 1}, "1": {"MEAL_VEG": 1}},
    )
    made = booking.create_booking(draft, wanjiru, payment.checkout_expiry(), reference="ANDEMO01")
    payment.pay_by_card(made, "4242")

    draft = _demo_draft(
        [("AN301", today + timedelta(days=9), "Economy", "Flex")],
        her_party[:1],
        "wanjiru@anga.example",
        "+254700000003",
    )
    made = booking.create_booking(
        draft,
        wanjiru,
        payment.pay_later_expiry(booking.draft_flights(draft)),
        reference="ANDEMO02",
    )
    payment.record_pay_later(made)

    with transaction():
        users_repo.add_traveller(wanjiru, "Daudi Kamau", "KE10293847", None)
        users_repo.add_traveller(wanjiru, "Neema Kamau", "KE55667788", "2019-05-14")

    # Her past trips, which also build up a Silver-tier miles balance.
    history = current_app.config["SCHEDULE_HISTORY_DAYS"]
    for days_ago, number, family in ((9, "AN301", "Flex"), (5, "AN101", "Classic")):
        if days_ago > history:
            continue
        flown = today - timedelta(days=days_ago)
        with clock.travel(datetime.combine(flown - timedelta(days=2), time(9, 30))):
            draft = _demo_draft(
                [(number, flown, "Business", family)],
                her_party,
                "wanjiru@anga.example",
                "+254700000003",
            )
            if draft:
                made = booking.create_booking(draft, wanjiru, payment.checkout_expiry())
                payment.pay_by_card(made, "4242")
    with transaction():
        users_repo.add_miles(wanjiru, None, 300, "Welcome bonus", clock.timestamp())

    # Other customers, spread across recent days so the dashboard charts have data.
    rng = random.Random(2026)
    routes = ["AN101", "AN102", "AN201", "AN202", "AN301", "AN302"]
    families = ["Lite", "Classic", "Classic", "Flex"]
    created = 0
    for index in range(40):
        if created >= DEMO_BOOKING_COUNT:
            break
        days_ago = index % max(history - 2, 1)
        created_at = datetime.combine(
            today - timedelta(days=days_ago), time(rng.randint(7, 20), rng.randint(0, 59))
        )
        created_at = min(created_at, now - timedelta(minutes=5))
        name = DEMO_PEOPLE[index % len(DEMO_PEOPLE)]
        email = f"{name.split()[0].lower()}{index}@demo.example"
        with clock.travel(created_at):
            draft = _demo_draft(
                [
                    (
                        rng.choice(routes),
                        created_at.date() + timedelta(days=rng.randint(2, 7)),
                        rng.choice(("Economy", "Economy", "Economy", "Business")),
                        rng.choice(families),
                    )
                ],
                [(name, f"ID{index:07d}")],
                email,
                "+254722000000",
            )
            if draft is None:
                continue
            made = booking.create_booking(draft, None, payment.checkout_expiry())
            payment.pay_by_card(made, "4242")
            created += 1


def seed_capacity_demo() -> None:
    """A nearly full flight, so the "last seats" states can be seen in the demo."""
    day = clock.today() + timedelta(days=3)
    flight = flights_repo.get_by_number("AN201", day.isoformat())
    with transaction():
        schedule.fill_cabin(flight["id"], "Economy", leave_free=2)


def seed_schedule() -> int:
    today = clock.today()
    schedule.generate_history(today, current_app.config["SCHEDULE_HISTORY_DAYS"], HISTORY_ROUTES)
    created = schedule.top_up(today, current_app.config["SCHEDULE_HORIZON_DAYS"])
    schedule.refresh_todays_board(clock.now())
    return created


def run(reset_first: bool = False) -> bool:
    """Seed the database; returns False if it already held data."""
    init_db()
    if reset_first:
        reset()
    elif is_seeded():
        return False
    seed_reference_data()
    seed_schedule()
    seed_promos()
    seed_demo_bookings(seed_users())
    seed_capacity_demo()
    settings_repo.put("seeded_at", clock.timestamp())
    get_db().execute("PRAGMA optimize")
    return True
