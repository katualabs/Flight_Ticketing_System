"""``flask --app anga ...`` commands."""

from __future__ import annotations

import click
from flask import Flask

from anga import db, seed
from anga.services import booking as booking_service
from anga.services import watches


def register(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create the database and apply migrations."""
        applied = db.init_db()
        click.echo(f"Applied: {', '.join(applied)}" if applied else "Already up to date.")

    @app.cli.command("seed")
    @click.option("--reset", is_flag=True, help="Erase all data first.")
    def seed_command(reset: bool) -> None:
        """Load demo data."""
        if seed.run(reset_first=reset):
            click.echo("Demo data loaded.")
        else:
            click.echo("Database already seeded. Use --reset to start over.")

    @app.cli.command("check-price-watches")
    def check_price_watches_command() -> None:
        """Raise alerts for watched trips that have become cheaper."""
        click.echo(f"Raised {watches.check()} alert(s).")

    @app.cli.command("expire-holds")
    def expire_holds_command() -> None:
        """Cancel unpaid bookings past their deadline."""
        click.echo(f"Expired {booking_service.expire_holds()} booking(s).")
