"""Shared fixtures."""

from __future__ import annotations

import pytest

from anga import create_app


@pytest.fixture
def app(tmp_path):
    return create_app("testing", {"DATABASE_PATH": str(tmp_path / "test.db")})


@pytest.fixture
def client(app):
    return app.test_client()
