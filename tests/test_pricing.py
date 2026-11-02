"""Pricing rules, tested as plain functions."""

from __future__ import annotations

from datetime import date

import pytest

from anga.services import pricing

MONDAY = date(2026, 3, 2)
SATURDAY = date(2026, 3, 7)


def test_round_price_uses_fifty_shilling_steps():
    assert pricing.round_price(8524) == 8500
    assert pricing.round_price(8526) == 8550


@pytest.mark.parametrize(
    ("cabin", "family", "expected"),
    [
        ("Economy", "Lite", 8500),
        ("Economy", "Classic", 10350),
        ("Economy", "Flex", 13200),
        ("Business", "Lite", 22100),
        ("First", "Lite", 35700),
    ],
)
def test_base_price_applies_cabin_and_family(cabin, family, expected):
    assert pricing.base_price(8500, cabin, family) == expected


@pytest.mark.parametrize(
    ("load", "multiplier"),
    [(0.0, 1.0), (0.59, 1.0), (0.60, 1.12), (0.84, 1.12), (0.85, 1.28), (1.0, 1.28)],
)
def test_demand_multiplier_thresholds(load, multiplier):
    assert pricing.demand_multiplier(load) == multiplier


def test_weekend_surge_applies_only_at_weekends():
    assert pricing.dynamic_price(10000, MONDAY, 0.0) == 10000
    assert pricing.dynamic_price(10000, SATURDAY, 0.0) == 11200


def test_weekend_and_demand_add_rather_than_compound():
    assert pricing.dynamic_price(10000, SATURDAY, 0.9) == 14000


def test_load_factor_handles_empty_cabin():
    assert pricing.load_factor(0, 0) == 0.0
    assert pricing.load_factor(100, 25) == 0.75


def test_passenger_multipliers():
    assert pricing.passenger_fare(10000, "adult") == 10000
    assert pricing.passenger_fare(10000, "child") == 7500
    assert pricing.passenger_fare(10000, "infant") == 1000


def test_fare_rules_describe_each_family():
    assert pricing.FARE_RULES["Lite"].can_change is False
    assert pricing.FARE_RULES["Classic"].change_fee > 0
    assert pricing.FARE_RULES["Flex"].refund_rate == 1.0
