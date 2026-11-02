"""Anga Air: online booking and operations platform for a fictional airline."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

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

    _register_blueprints(app)
    return app


def _register_blueprints(app: Flask) -> None:
    from anga.blueprints.public import bp as public_bp

    app.register_blueprint(public_bp)
