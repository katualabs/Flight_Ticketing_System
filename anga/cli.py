"""``flask --app anga ...`` commands."""

from __future__ import annotations

import click
from flask import Flask

from anga import db, seed


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
