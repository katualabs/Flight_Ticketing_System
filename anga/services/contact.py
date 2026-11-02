"""Contact form handling: stored for staff, with a copy to the outbox."""

from __future__ import annotations

from anga import clock
from anga.db import transaction
from anga.repositories import messages as messages_repo
from anga.services import notifications

SUPPORT_ADDRESS = "hello@anga.example"


def submit(data: dict) -> int:
    with transaction():
        message_id = messages_repo.insert(
            data["full_name"], data["email"], data["subject"], data["body"], clock.timestamp()
        )
        notifications.send(
            SUPPORT_ADDRESS,
            f"Contact form: {data['subject']}",
            "contact",
            full_name=data["full_name"],
            email=data["email"],
            body=data["body"],
        )
    return message_id
