"""SQL for accounts, saved travellers and the miles ledger."""

from __future__ import annotations

from sqlite3 import Row

from anga.db import execute, fetch_all, fetch_one, fetch_value


def insert(
    full_name: str,
    email: str,
    phone: str | None,
    password_hash: str,
    role: str,
    created_at: str,
) -> int:
    cursor = execute(
        "INSERT INTO users (full_name, email, phone, password_hash, role, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (full_name, email, phone, password_hash, role, created_at),
    )
    return cursor.lastrowid


def get(user_id: int) -> Row | None:
    return fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))


def get_by_email(email: str) -> Row | None:
    return fetch_one("SELECT * FROM users WHERE email = ?", (email,))


def record_login(user_id: int, moment: str) -> None:
    execute("UPDATE users SET last_login = ? WHERE id = ?", (moment, user_id))


def update_profile(user_id: int, full_name: str, phone: str | None) -> None:
    execute("UPDATE users SET full_name = ?, phone = ? WHERE id = ?", (full_name, phone, user_id))


def update_password(user_id: int, password_hash: str) -> None:
    execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def add_miles(user_id: int, booking_id: int | None, delta: int, reason: str, moment: str) -> None:
    """Ledger row and balance move together, and callers wrap this in a transaction."""
    execute(
        "INSERT INTO miles_ledger (user_id, booking_id, delta, reason, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (user_id, booking_id, delta, reason, moment),
    )
    execute("UPDATE users SET miles_balance = miles_balance + ? WHERE id = ?", (delta, user_id))


def miles_ledger(user_id: int) -> list[Row]:
    return fetch_all(
        "SELECT m.*, b.reference FROM miles_ledger m"
        " LEFT JOIN bookings b ON b.id = m.booking_id"
        " WHERE m.user_id = ? ORDER BY m.created_at DESC, m.id DESC",
        (user_id,),
    )


def miles_earned_for_booking(booking_id: int) -> int:
    value = fetch_value(
        "SELECT COALESCE(SUM(delta), 0) FROM miles_ledger WHERE booking_id = ?", (booking_id,)
    )
    return int(value)


def saved_travellers(user_id: int) -> list[Row]:
    return fetch_all(
        "SELECT * FROM saved_travellers WHERE user_id = ? ORDER BY full_name", (user_id,)
    )


def add_traveller(user_id: int, full_name: str, id_number: str, date_of_birth: str | None) -> int:
    cursor = execute(
        "INSERT INTO saved_travellers (user_id, full_name, id_number, date_of_birth)"
        " VALUES (?, ?, ?, ?)",
        (user_id, full_name, id_number, date_of_birth),
    )
    return cursor.lastrowid


def delete_traveller(user_id: int, traveller_id: int) -> bool:
    """Scoped to the owner, so one customer can never delete another's traveller."""
    cursor = execute(
        "DELETE FROM saved_travellers WHERE id = ? AND user_id = ?", (traveller_id, user_id)
    )
    return cursor.rowcount == 1


def login_attempt(email: str) -> Row | None:
    return fetch_one("SELECT * FROM login_attempts WHERE email = ?", (email,))


def increment_login_failures(email: str) -> int:
    execute(
        "INSERT INTO login_attempts (email, failures) VALUES (?, 1)"
        " ON CONFLICT (email) DO UPDATE SET failures = failures + 1",
        (email,),
    )
    return fetch_value("SELECT failures FROM login_attempts WHERE email = ?", (email,))


def lock_login(email: str, until: str) -> None:
    """Start a lockout and reset the count, so the next window starts afresh."""
    execute(
        "UPDATE login_attempts SET locked_until = ?, failures = 0 WHERE email = ?", (until, email)
    )


def clear_login_attempts(email: str) -> None:
    execute("DELETE FROM login_attempts WHERE email = ?", (email,))


def list_all(query: str | None, limit: int, offset: int) -> tuple[list[Row], int]:
    where, params = "", []
    if query:
        where = "WHERE u.email LIKE ? OR u.full_name LIKE ?"
        params = [f"%{query}%", f"%{query}%"]
    total = fetch_value(f"SELECT COUNT(*) FROM users u {where}", params)
    rows = fetch_all(
        f"SELECT u.*, (SELECT COUNT(*) FROM bookings b WHERE b.user_id = u.id) AS booking_count"
        f" FROM users u {where} ORDER BY u.created_at DESC, u.id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    return rows, total


def update_role(user_id: int, role: str) -> None:
    execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def set_disabled(user_id: int, disabled: bool) -> None:
    execute("UPDATE users SET disabled = ? WHERE id = ?", (int(disabled), user_id))
