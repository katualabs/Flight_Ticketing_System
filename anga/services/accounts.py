"""Account rules: registration, sign-in and profile changes."""

from __future__ import annotations

from sqlite3 import Row

from flask import current_app
from werkzeug.security import generate_password_hash

from anga import clock
from anga.repositories import users as users_repo


def hash_password(password: str) -> str:
    return generate_password_hash(password, method=current_app.config["HASH_METHOD"])


def active_user(user_id: int) -> Row | None:
    return users_repo.get(user_id)


def create_user(
    full_name: str, email: str, phone: str | None, password: str, role: str = "customer"
) -> int:
    return users_repo.insert(
        full_name, email.lower(), phone, hash_password(password), role, clock.timestamp()
    )
