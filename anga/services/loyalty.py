"""Anga Miles: earning, reversing and tier rules."""

from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Row

from anga import clock
from anga.repositories import users as users_repo

KSH_PER_MILE = 100
SILVER_MILES = 500
GOLD_MILES = 2000


@dataclass(frozen=True)
class Tier:
    name: str
    css_class: str
    next_name: str | None
    miles_to_next: int


def miles_for(amount: int) -> int:
    return max(0, amount) // KSH_PER_MILE


def tier_for(balance: int) -> Tier:
    if balance >= GOLD_MILES:
        return Tier("Gold", "tier-gold", None, 0)
    if balance >= SILVER_MILES:
        return Tier("Silver", "tier-silver", "Gold", GOLD_MILES - balance)
    return Tier("Member", "tier-member", "Silver", SILVER_MILES - balance)


def earn_for_booking(booking: Row) -> int:
    """Credit miles for a confirmed booking. Guests have no account, so earn nothing."""
    if booking["user_id"] is None:
        return 0
    miles = miles_for(booking["total"])
    if miles:
        users_repo.add_miles(
            booking["user_id"],
            booking["id"],
            miles,
            f"Earned on booking {booking['reference']}",
            clock.timestamp(),
        )
    return miles


def reverse_for_booking(booking: Row) -> int:
    """Take back whatever a cancelled booking earned."""
    if booking["user_id"] is None:
        return 0
    earned = users_repo.miles_earned_for_booking(booking["id"])
    if earned > 0:
        users_repo.add_miles(
            booking["user_id"],
            booking["id"],
            -earned,
            f"Reversed: booking {booking['reference']} cancelled",
            clock.timestamp(),
        )
    return earned
