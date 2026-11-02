"""App factory behaviour."""

from __future__ import annotations

import pytest

from anga import create_app


def test_home_responds(client):
    assert client.get("/").status_code == 200


def test_production_requires_a_secret_key(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production", {"SECRET_KEY": None, "DATABASE_PATH": str(tmp_path / "x.db")})


def test_testing_config_is_applied(app):
    assert app.config["TESTING"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
