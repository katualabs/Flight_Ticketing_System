"""Work that runs alongside requests: first-run setup and periodic cleanup."""

from __future__ import annotations

import threading
import time

from flask import Flask, current_app, request

from anga import clock, db, seed
from anga.services import booking as booking_service
from anga.services import schedule

_setup_lock = threading.Lock()


def _prepare_database() -> None:
    """Migrate, seed if empty and top up the schedule, once per process."""
    db.init_db()
    if current_app.config["AUTO_SEED"] and not seed.is_seeded():
        seed.run()
    elif seed.is_seeded():
        schedule.top_up(clock.today(), current_app.config["SCHEDULE_HORIZON_DAYS"])
        schedule.refresh_todays_board(clock.now())


def init_app(app: Flask) -> None:
    state = {"ready": False, "last_cleanup": 0.0}

    @app.before_request
    def _before_first_request() -> None:
        if state["ready"] or request.endpoint == "static":
            return
        with _setup_lock:
            if not state["ready"]:
                _prepare_database()
                state["ready"] = True

    @app.before_request
    def _periodic_cleanup() -> None:
        """Expire unpaid holds at most once a minute, so no cron job is required."""
        if request.endpoint == "static":
            return
        moment = time.monotonic()
        if moment - state["last_cleanup"] >= app.config["CLEANUP_INTERVAL_SECONDS"]:
            state["last_cleanup"] = moment
            booking_service.expire_holds()
