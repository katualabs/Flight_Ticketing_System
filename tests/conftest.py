"""Shared fixtures.

Seeding once per session and copying the file per test gives every test a
pristine, fully populated database at the cost of a file copy.
"""

from __future__ import annotations

import shutil
from datetime import datetime

import pytest

from anga import clock, create_app, seed

FIXED_NOW = datetime(2026, 3, 2, 10, 0, 0)  # a Monday


@pytest.fixture(autouse=True)
def frozen_clock():
    clock.freeze(FIXED_NOW)
    yield
    clock.freeze(None)


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory):
    clock.freeze(FIXED_NOW)
    path = tmp_path_factory.mktemp("template") / "seed.db"
    app = create_app("testing", {"DATABASE_PATH": str(path)})
    with app.app_context():
        seed.run()
    clock.freeze(None)
    return path


@pytest.fixture
def app(tmp_path, seeded_template):
    path = tmp_path / "test.db"
    shutil.copyfile(seeded_template, path)
    return create_app("testing", {"DATABASE_PATH": str(path)})


@pytest.fixture
def empty_app(tmp_path):
    return create_app("testing", {"DATABASE_PATH": str(tmp_path / "empty.db")})


@pytest.fixture
def seeded(app):
    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    return app.test_client()
