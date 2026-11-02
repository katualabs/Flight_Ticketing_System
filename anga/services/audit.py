"""Records who did what in the operations console."""

from __future__ import annotations

import json
from sqlite3 import Row

from anga import clock
from anga.repositories import audit as audit_repo


def record(
    actor_id: int | None, action: str, entity: str, entity_id: object = None, **details
) -> None:
    audit_repo.insert(
        actor_id,
        action,
        entity,
        None if entity_id is None else str(entity_id),
        json.dumps(details, default=str),
        clock.timestamp(),
    )


def search(
    action: str | None, entity: str | None, limit: int, offset: int = 0
) -> tuple[list[Row], int]:
    return audit_repo.search(action, entity, limit, offset)


def actions() -> list[str]:
    return audit_repo.distinct_actions()
