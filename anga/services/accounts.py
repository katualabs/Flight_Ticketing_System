"""Account rules: registration, sign-in lockout, profiles and trips."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlite3 import IntegrityError, Row

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from anga import clock
from anga.repositories import bookings as bookings_repo
from anga.repositories import users as users_repo
from anga.services.booking import flight_departure

# Compared against when an email is unknown, so a login takes the same time
# whether or not the account exists.
_DUMMY_HASH: dict[str, str] = {}


class AccountError(Exception):
    """The message is safe to show the user."""


def hash_password(password: str) -> str:
    return generate_password_hash(password, method=current_app.config["HASH_METHOD"])


def active_user(user_id: int) -> Row | None:
    """A user who is allowed a session: disabling an account signs it out at once."""
    user = users_repo.get(user_id)
    return user if user is not None and not user["disabled"] else None


def create_user(
    full_name: str, email: str, phone: str | None, password: str, role: str = "customer"
) -> int:
    return users_repo.insert(
        full_name, email.lower(), phone, hash_password(password), role, clock.timestamp()
    )


def register(data: dict) -> int:
    """Create a customer account from validated data."""
    try:
        return create_user(data["full_name"], data["email"], data["phone"], data["password"])
    except IntegrityError as error:
        raise AccountError("An account with that email already exists.") from error


def _is_locked(email: str, now: datetime) -> bool:
    row = users_repo.login_attempt(email)
    return bool(row and row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > now)


def authenticate(email: str, password: str) -> Row:
    """Check credentials, with a temporary lockout after repeated failures.

    Every failure raises the same message, so the response never reveals
    whether an account exists.
    """
    now = clock.now()
    email = email.strip().lower()
    if _is_locked(email, now):
        raise AccountError(
            "Too many failed attempts. Please wait a few minutes before trying again."
        )
    user = users_repo.get_by_email(email)
    stored = user["password_hash"] if user else _dummy_hash()
    if user is None or not check_password_hash(stored, password) or user["disabled"]:
        _record_failure(email, now)
        raise AccountError("That email and password do not match.")
    users_repo.clear_login_attempts(email)
    users_repo.record_login(user["id"], clock.timestamp())
    return user


def _dummy_hash() -> str:
    method = current_app.config["HASH_METHOD"]
    if method not in _DUMMY_HASH:
        _DUMMY_HASH[method] = generate_password_hash("not-a-real-password", method=method)
    return _DUMMY_HASH[method]


def _record_failure(email: str, now: datetime) -> None:
    config = current_app.config
    failures = users_repo.increment_login_failures(email)
    if failures >= config["LOGIN_MAX_ATTEMPTS"]:
        until = now + timedelta(minutes=config["LOGIN_LOCKOUT_MINUTES"])
        users_repo.lock_login(email, until.isoformat(timespec="seconds"))


def update_profile(user_id: int, full_name: str, phone: str | None) -> None:
    users_repo.update_profile(user_id, full_name, phone)


def change_password(user: Row, current: str, new: str) -> None:
    if not check_password_hash(user["password_hash"], current):
        raise AccountError("Your current password is not correct.")
    users_repo.update_password(user["id"], hash_password(new))


def saved_travellers(user_id: int) -> list[Row]:
    return users_repo.saved_travellers(user_id)


def add_traveller(user_id: int, data: dict) -> int:
    return users_repo.add_traveller(
        user_id, data["full_name"], data["id_number"], data["date_of_birth"]
    )


def delete_traveller(user_id: int, traveller_id: int) -> bool:
    return users_repo.delete_traveller(user_id, traveller_id)


def miles_ledger(user_id: int) -> list[Row]:
    return users_repo.miles_ledger(user_id)


@dataclass
class Trip:
    booking: Row
    segments: list[Row]

    @property
    def first(self) -> Row:
        return self.segments[0]

    @property
    def last(self) -> Row:
        return self.segments[-1]


def trips_for(user_id: int) -> tuple[list[Trip], list[Trip]]:
    """A customer's bookings as (upcoming, past or cancelled)."""
    now = clock.now()
    upcoming, past = [], []
    for booking in bookings_repo.for_user(user_id):
        trip = Trip(booking, bookings_repo.segments(booking["id"]))
        finished = flight_departure(trip.last) < now
        if booking["status"] == "Cancelled" or finished:
            past.append(trip)
        else:
            upcoming.append(trip)
    upcoming.sort(key=lambda trip: flight_departure(trip.first))
    return upcoming, past
