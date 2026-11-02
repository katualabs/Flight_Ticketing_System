"""Environment-specific configuration, resolved once at app start."""

from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def load_or_create_secret_key(instance_path: Path) -> str:
    """Return a stable development key without ever committing one.

    Generating into ``instance/`` (git-ignored) keeps sessions valid across
    restarts while leaving no secret in the repository.
    """
    key_file = instance_path / "secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    instance_path.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    return key


class Config:
    """Defaults shared by every environment."""

    ENV_NAME = "base"
    TESTING = False
    DEBUG = False

    SECRET_KEY = os.environ.get("SECRET_KEY") or None
    DATABASE_PATH = os.environ.get("DATABASE_PATH") or None

    MAX_CONTENT_LENGTH = 512 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_NAME = "anga_session"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    HASH_METHOD = "scrypt"
    AUTO_SEED = True
    SCHEDULE_HORIZON_DAYS = 45
    SCHEDULE_HISTORY_DAYS = 28

    MPESA_SIM_SECONDS = int(os.environ.get("MPESA_SIM_SECONDS", "4"))
    CLEANUP_INTERVAL_SECONDS = 60
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_LOCKOUT_MINUTES = 15
    LOOKUP_RATE_PER_MINUTE = 20
    LOOKUP_RATE_BURST = 10
    API_RATE_PER_MINUTE = 120
    API_RATE_BURST = 40


class DevelopmentConfig(Config):
    ENV_NAME = "development"
    DEBUG = True


class TestingConfig(Config):
    ENV_NAME = "testing"
    TESTING = True
    SECRET_KEY = "test-secret-key"  # noqa: S105 - only ever used by the test suite
    AUTO_SEED = False
    HASH_METHOD = "pbkdf2:sha256:1000"
    SCHEDULE_HORIZON_DAYS = 21
    SCHEDULE_HISTORY_DAYS = 10
    MPESA_SIM_SECONDS = 0
    CLEANUP_INTERVAL_SECONDS = 0
    LOOKUP_RATE_PER_MINUTE = 6000
    LOOKUP_RATE_BURST = 1000
    API_RATE_PER_MINUTE = 6000
    API_RATE_BURST = 1000


class ProductionConfig(Config):
    ENV_NAME = "production"
    SESSION_COOKIE_SECURE = True


CONFIGS: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
