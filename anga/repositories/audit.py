"""SQL for the audit trail."""

from __future__ import annotations

from sqlite3 import Row

from anga.db import execute, fetch_all, fetch_value


def insert(
    actor_user_id: int | None,
    action: str,
    entity: str,
    entity_id: str | None,
    details: str,
    created_at: str,
) -> None:
    execute(
        "INSERT INTO audit_log (actor_user_id, action, entity, entity_id, details, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (actor_user_id, action, entity, entity_id, details, created_at),
    )


def search(
    action: str | None, entity: str | None, limit: int, offset: int = 0
) -> tuple[list[Row], int]:
    clauses, params = [], []
    if action:
        clauses.append("a.action = ?")
        params.append(action)
    if entity:
        clauses.append("a.entity = ?")
        params.append(entity)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = fetch_value(f"SELECT COUNT(*) FROM audit_log a {where}", params)
    rows = fetch_all(
        f"SELECT a.*, u.email AS actor_email FROM audit_log a"
        f" LEFT JOIN users u ON u.id = a.actor_user_id {where}"
        " ORDER BY a.created_at DESC, a.id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    return rows, total


def distinct_actions() -> list[str]:
    return [row[0] for row in fetch_all("SELECT DISTINCT action FROM audit_log ORDER BY action")]
