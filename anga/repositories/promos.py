"""SQL for promo codes."""

from __future__ import annotations

from sqlite3 import Row

from anga.db import execute, fetch_all, fetch_one


def get_by_code(code: str) -> Row | None:
    return fetch_one("SELECT * FROM promo_codes WHERE code = ?", (code,))


def get(promo_id: int) -> Row | None:
    return fetch_one("SELECT * FROM promo_codes WHERE id = ?", (promo_id,))


def all_promos() -> list[Row]:
    return fetch_all(
        "SELECT p.*, COALESCE(SUM(b.discount), 0) AS total_discount"
        " FROM promo_codes p"
        " LEFT JOIN bookings b ON b.promo_id = p.id AND b.status <> 'Cancelled'"
        " GROUP BY p.id ORDER BY p.valid_to DESC, p.code"
    )


def insert(
    code: str,
    kind: str,
    value: int,
    scope: str,
    min_spend: int,
    valid_from: str,
    valid_to: str,
    max_uses: int | None,
    active: int = 1,
) -> int:
    cursor = execute(
        "INSERT INTO promo_codes (code, kind, value, scope, min_spend, valid_from, valid_to,"
        " max_uses, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (code, kind, value, scope, min_spend, valid_from, valid_to, max_uses, active),
    )
    return cursor.lastrowid


def update(
    promo_id: int,
    code: str,
    kind: str,
    value: int,
    scope: str,
    min_spend: int,
    valid_from: str,
    valid_to: str,
    max_uses: int | None,
    active: int,
) -> None:
    execute(
        "UPDATE promo_codes SET code = ?, kind = ?, value = ?, scope = ?, min_spend = ?,"
        " valid_from = ?, valid_to = ?, max_uses = ?, active = ? WHERE id = ?",
        (code, kind, value, scope, min_spend, valid_from, valid_to, max_uses, active, promo_id),
    )


def delete(promo_id: int) -> None:
    execute("DELETE FROM promo_codes WHERE id = ?", (promo_id,))


def count_bookings(promo_id: int) -> int:
    return fetch_one("SELECT COUNT(*) AS n FROM bookings WHERE promo_id = ?", (promo_id,))["n"]


def claim_use(promo_id: int) -> bool:
    """Count a use only if the limit still allows it, so a cap cannot be overrun."""
    cursor = execute(
        "UPDATE promo_codes SET used_count = used_count + 1"
        " WHERE id = ? AND (max_uses IS NULL OR used_count < max_uses)",
        (promo_id,),
    )
    return cursor.rowcount == 1


def release_use(promo_id: int) -> None:
    execute("UPDATE promo_codes SET used_count = MAX(0, used_count - 1) WHERE id = ?", (promo_id,))
