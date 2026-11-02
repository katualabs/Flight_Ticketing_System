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


TODAY = date(2026, 3, 2)


def promo(**overrides):
    base = {
        "code": "SAVE",
        "kind": "percent",
        "value": 10,
        "scope": "all",
        "min_spend": 0,
        "valid_from": "2026-01-01",
        "valid_to": "2026-12-31",
        "max_uses": None,
        "used_count": 0,
        "active": 1,
    }
    return {**base, **overrides}


def test_percent_promo():
    result = pricing.evaluate_promo(promo(), 10000, False, TODAY)
    assert result.ok
    assert result.discount == 1000


def test_fixed_promo_cannot_exceed_subtotal():
    result = pricing.evaluate_promo(promo(kind="fixed", value=5000), 3000, False, TODAY)
    assert result.discount == 3000


@pytest.mark.parametrize(
    ("overrides", "subtotal", "coastal", "fragment"),
    [
        ({"active": 0}, 10000, False, "not valid"),
        ({"valid_to": "2026-03-01"}, 10000, False, "expired"),
        ({"valid_from": "2026-03-03"}, 10000, False, "expired"),
        ({"max_uses": 5, "used_count": 5}, 10000, False, "usage limit"),
        ({"min_spend": 10001}, 10000, False, "minimum spend"),
        ({"scope": "coastal"}, 10000, False, "coastal"),
    ],
)
def test_promo_rejections(overrides, subtotal, coastal, fragment):
    result = pricing.evaluate_promo(promo(**overrides), subtotal, coastal, TODAY)
    assert not result.ok
    assert result.discount == 0
    assert fragment in result.message


def test_unknown_promo_is_rejected():
    assert not pricing.evaluate_promo(None, 10000, False, TODAY).ok


def test_coastal_promo_accepts_coastal_route():
    assert pricing.evaluate_promo(promo(scope="coastal"), 10000, True, TODAY).ok


def test_promo_at_exact_min_spend_and_last_valid_day():
    assert pricing.evaluate_promo(promo(min_spend=10000), 10000, False, TODAY).ok
    assert pricing.evaluate_promo(promo(valid_to=TODAY.isoformat()), 10000, False, TODAY).ok


def test_lite_cannot_change():
    quote = pricing.change_quote("Lite", 8000, 9000)
    assert not quote.allowed
    assert quote.reason


def test_classic_change_pays_fee_and_difference():
    quote = pricing.change_quote("Classic", 10000, 12000)
    assert quote.allowed
    assert quote.fee == 3000
    assert quote.difference == 2000
    assert quote.total == 5000


def test_classic_cheaper_flight_gives_no_refund():
    assert pricing.change_quote("Classic", 12000, 10000).total == 3000


def test_flex_change_is_free():
    assert pricing.change_quote("Flex", 10000, 20000).total == 0


def refund(segments, **overrides):
    args = {
        "subtotal": sum(fare for _, fare in segments),
        "discount": 0,
        "seats_total": 0,
        "extras_total": 0,
        "amount_paid": 100000,
        "hours_to_departure": 72,
        "window_hours": 3,
    }
    return pricing.refund_quote(segments, **{**args, **overrides})


def test_lite_refunds_nothing():
    assert refund([("Lite", 10000)]).amount == 0


def test_classic_refunds_half():
    assert refund([("Classic", 10000)]).amount == 5000


def test_flex_refunds_fare_seats_and_extras():
    assert refund([("Flex", 10000)], seats_total=600, extras_total=900).amount == 11500


def test_mixed_booking_keeps_ancillaries():
    assert refund([("Flex", 10000), ("Lite", 8000)], extras_total=900).amount == 10000


def test_discount_reduces_refund_proportionally():
    assert refund([("Flex", 10000)], discount=1000).amount == 9000


def test_no_refund_inside_cancellation_window():
    quote = refund([("Flex", 10000)], hours_to_departure=2)
    assert quote.amount == 0
    assert "3 hours" in quote.reason


def test_unpaid_booking_refunds_nothing():
    assert refund([("Flex", 10000)], amount_paid=0).amount == 0


def test_refund_never_exceeds_amount_paid():
    assert refund([("Flex", 10000)], amount_paid=4000).amount == 4000
