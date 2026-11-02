"""Price-drop watches: alert a customer when a trip gets cheaper than they saw it."""

from __future__ import annotations

from datetime import date
from sqlite3 import Row

from anga import clock
from anga.db import transaction
from anga.repositories import users as users_repo
from anga.repositories import watches as watches_repo
from anga.services import notifications, search


class WatchError(Exception):
    """The message is safe to show the customer."""


def create(user_id: int, origin: str, destination: str, day: date, cabin: str) -> int:
    """Start watching a trip from today's cheapest fare; returns that fare."""
    price = search.cheapest_on(origin, destination, day, cabin)
    if price is None:
        raise WatchError("There are no fares to watch on that date.")
    watches_repo.upsert(
        user_id, origin, destination, day.isoformat(), cabin, price, clock.timestamp()
    )
    return price


def for_user(user_id: int) -> list[Row]:
    return watches_repo.for_user(user_id)


def dismiss(user_id: int, watch_id: int) -> bool:
    return watches_repo.dismiss(user_id, watch_id)


def check(user_id: int | None = None) -> int:
    """Compare pending watches to live fares; returns how many alerts were raised.

    Runs when a customer opens their dashboard and from the CLI, so it needs no
    background worker. A watch alerts once, because ``pending`` skips it afterwards.
    """
    raised = 0
    for watch in watches_repo.pending(clock.today().isoformat(), user_id):
        price = search.cheapest_on(
            watch["origin"],
            watch["destination"],
            date.fromisoformat(watch["travel_date"]),
            watch["cabin"],
        )
        if price is None or price >= watch["seen_price"]:
            continue
        with transaction():
            watches_repo.mark_alerted(watch["id"], price, clock.timestamp())
            user = users_repo.get(watch["user_id"])
            notifications.send(
                user["email"],
                f"Price drop: {watch['origin_city']} to {watch['destination_city']}",
                "price_drop",
                watch=watch,
                price=price,
            )
        raised += 1
    return raised
