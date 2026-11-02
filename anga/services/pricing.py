"""Every pricing and fare rule in the airline, free of Flask and SQL.

Keeping these as pure functions means a rule such as "Classic pays a change fee
plus the fare difference" can be tested with plain numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

CABINS = ("Economy", "Business", "First")
FAMILIES = ("Lite", "Classic", "Flex")

CABIN_MULTIPLIER = {"Economy": 1.0, "Business": 2.6, "First": 4.2}
FAMILY_MULTIPLIER = {"Lite": 1.0, "Classic": 1.22, "Flex": 1.55}
PASSENGER_MULTIPLIER = {"adult": 1.0, "child": 0.75, "infant": 0.10}

WEEKEND_SURGE = 0.12
DEMAND_STEPS = ((0.85, 0.28), (0.60, 0.12))
ROUND_TO = 50


@dataclass(frozen=True)
class FamilyRules:
    """What a fare family includes and allows."""

    name: str
    bags: int
    can_change: bool
    change_fee: int
    refund_rate: float
    summary: str


FARE_RULES = {
    "Lite": FamilyRules("Lite", 0, False, 0, 0.0, "Cabin bag only. No changes, no refund."),
    "Classic": FamilyRules(
        "Classic", 1, True, 3000, 0.5, "1 checked bag. Change for KSh 3,000. 50% refund."
    ),
    "Flex": FamilyRules("Flex", 2, True, 0, 1.0, "2 checked bags. Free changes. Fully refundable."),
}


def round_price(amount: float) -> int:
    """Round to the nearest KSh 50, the way fares are displayed and charged."""
    return int(round(amount / ROUND_TO) * ROUND_TO)


def base_price(route_base: int, cabin: str, family: str) -> int:
    """Stored price of a fare before date and demand adjustments."""
    return round_price(route_base * CABIN_MULTIPLIER[cabin] * FAMILY_MULTIPLIER[family])


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def demand_multiplier(load_factor: float) -> float:
    """Price rises as a cabin fills: past 60% and again past 85%."""
    for threshold, uplift in DEMAND_STEPS:
        if load_factor >= threshold:
            return 1 + uplift
    return 1.0


def load_factor(total_seats: int, available_seats: int) -> float:
    if total_seats <= 0:
        return 0.0
    return (total_seats - available_seats) / total_seats


def dynamic_price(price: int, day: date, load: float) -> int:
    """The price a customer actually sees for a fare today."""
    multiplier = demand_multiplier(load)
    if is_weekend(day):
        multiplier += WEEKEND_SURGE
    return round_price(price * multiplier)


def passenger_fare(price: int, passenger_type: str) -> int:
    return round_price(price * PASSENGER_MULTIPLIER[passenger_type])
