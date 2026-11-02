"""Every pricing and fare rule in the airline, free of Flask and SQL.

Keeping these as pure functions means a rule such as "Classic pays a change fee
plus the fare difference" can be tested with plain numbers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
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


@dataclass(frozen=True)
class PromoResult:
    ok: bool
    discount: int
    message: str


def evaluate_promo(
    promo: Mapping | None, subtotal: int, coastal_route: bool, today: date
) -> PromoResult:
    """Decide whether a promo code applies to this basket, and for how much."""
    if promo is None or not promo["active"]:
        return PromoResult(False, 0, "That promo code is not valid.")
    if not promo["valid_from"] <= today.isoformat() <= promo["valid_to"]:
        return PromoResult(False, 0, "That promo code has expired.")
    if promo["max_uses"] is not None and promo["used_count"] >= promo["max_uses"]:
        return PromoResult(False, 0, "That promo code has reached its usage limit.")
    if promo["scope"] == "coastal" and not coastal_route:
        return PromoResult(False, 0, "That promo code is only valid on coastal routes.")
    if subtotal < promo["min_spend"]:
        return PromoResult(
            False, 0, f"That promo code needs a minimum spend of KSh {promo['min_spend']:,}."
        )
    if promo["kind"] == "percent":
        discount = round(subtotal * promo["value"] / 100)
    else:
        discount = min(promo["value"], subtotal)
    return PromoResult(True, discount, f"{promo['code']} applied: KSh {discount:,} off.")


@dataclass(frozen=True)
class ChangeQuote:
    allowed: bool
    fee: int = 0
    difference: int = 0
    reason: str = ""

    @property
    def total(self) -> int:
        return self.fee + self.difference


def change_quote(family: str, old_fare_total: int, new_fare_total: int) -> ChangeQuote:
    """What moving to another flight costs under each fare family.

    A cheaper new flight never produces a refund; Flex changes are free outright.
    """
    rules = FARE_RULES[family]
    if not rules.can_change:
        return ChangeQuote(False, reason="Lite fares cannot be changed.")
    if rules.change_fee == 0:
        return ChangeQuote(True)
    return ChangeQuote(True, rules.change_fee, max(0, new_fare_total - old_fare_total))


@dataclass(frozen=True)
class RefundQuote:
    amount: int
    reason: str


def refund_quote(
    segments: Iterable[tuple[str, int]],
    subtotal: int,
    discount: int,
    seats_total: int,
    extras_total: int,
    amount_paid: int,
    hours_to_departure: float,
    window_hours: int,
) -> RefundQuote:
    """Refund due on cancellation, from ``(family, fare_paid)`` per segment.

    The promo discount is shared across the fare proportionally, seats and
    extras come back only on an all-Flex booking, and the result can never
    exceed what was actually paid.
    """
    if amount_paid <= 0:
        return RefundQuote(0, "Nothing has been paid on this booking.")
    if hours_to_departure < window_hours:
        return RefundQuote(0, f"Cancelled within {window_hours} hours of departure: no refund.")
    segments = list(segments)
    fare_refund = sum(fare * FARE_RULES[family].refund_rate for family, fare in segments)
    if subtotal > 0:
        fare_refund *= 1 - discount / subtotal
    all_flex = all(family == "Flex" for family, _ in segments)
    ancillaries = seats_total + extras_total if all_flex else 0
    amount = min(amount_paid, round(fare_refund + ancillaries))
    if amount == 0:
        return RefundQuote(0, "Lite fares are non-refundable.")
    return RefundQuote(amount, "Refund calculated from your fare rules.")
