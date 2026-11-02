"""Anga Air: online booking and operations platform for a fictional airline."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from anga import cli, db, errors, housekeeping, security, templating
from anga.config import CONFIGS, load_or_create_secret_key


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    """Build a configured application.

    ``overrides`` lets tests point at a temporary database without having to
    mutate environment variables.
    """
    app = Flask(__name__, instance_relative_config=True)
    name = config_name or os.environ.get("ANGA_ENV", "development")
    app.config.from_object(CONFIGS[name])
    app.config.update(overrides or {})

    instance_path = Path(app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)
    if not app.config.get("DATABASE_PATH"):
        app.config["DATABASE_PATH"] = str(instance_path / "anga_air.db")
    if not app.config.get("SECRET_KEY"):
        if name == "production":
            raise RuntimeError("SECRET_KEY must be set in production.")
        app.config["SECRET_KEY"] = load_or_create_secret_key(instance_path)

    db.init_app(app)
    # Housekeeping first: its first-run migration must precede anything using the database.
    housekeeping.init_app(app)
    security.init_app(app)
    templating.init_app(app)
    errors.init_app(app)
    _register_blueprints(app)
    cli.register(app)
    return app


def _register_blueprints(app: Flask) -> None:
    from anga.blueprints.api import bp as api_bp
    from anga.blueprints.booking import bp as booking_bp
    from anga.blueprints.public import bp as public_bp
    from anga.blueprints.search import bp as search_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(api_bp)
