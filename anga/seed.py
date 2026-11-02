"""Demo data. Everything is generated relative to today so the demo never goes stale."""

from __future__ import annotations

import json
from datetime import timedelta

from flask import current_app

from anga import clock
from anga.db import get_db, init_db, transaction
from anga.repositories import airports as airports_repo
from anga.repositories import extras as extras_repo
from anga.repositories import flights as flights_repo
from anga.repositories import promos as promos_repo
from anga.repositories import settings as settings_repo
from anga.services import schedule

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
    settings_repo.put("seeded_at", clock.timestamp())
    get_db().execute("PRAGMA optimize")
    return True
