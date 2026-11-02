"""Database plumbing: transactions, constraints and the migrations runner."""

from __future__ import annotations

import sqlite3

import pytest

from anga import db


@pytest.fixture
def ctx(empty_app):
    with empty_app.app_context():
        db.init_db()
        yield


def test_migrations_apply_once(ctx):
    assert db.init_db() == []
    versions = [r["version"] for r in db.fetch_all("SELECT version FROM schema_migrations")]
    assert db.BASELINE_VERSION in versions


def test_failed_migration_rolls_back(ctx, tmp_path, monkeypatch):
    bad = tmp_path / "9999_bad.sql"
    bad.write_text("CREATE TABLE half_done (id INTEGER); SELECT nonsense FROM nowhere;")
    monkeypatch.setattr(db, "MIGRATIONS_DIR", tmp_path)
    with pytest.raises(sqlite3.Error):
        db.init_db()
    assert db.fetch_one("SELECT name FROM sqlite_master WHERE name = 'half_done'") is None
    assert not db.get_db().in_transaction


def test_foreign_keys_are_enforced(ctx):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO flights (flight_number, departure_date, origin, destination,"
            " departure_time, arrival_time, duration_minutes, aircraft_code)"
            " VALUES ('AN1', '2030-01-01', 'XXX', 'YYY', '08:00', '09:00', 60, 'none')"
        )


def test_wal_mode_is_enabled(ctx):
    assert db.fetch_value("PRAGMA journal_mode") == "wal"


def test_transaction_commits(ctx):
    with db.transaction():
        db.execute("INSERT INTO settings (key, value) VALUES ('a', '1')")
    assert db.fetch_value("SELECT value FROM settings WHERE key = 'a'") == "1"


def test_transaction_rolls_back_on_error(ctx):
    with pytest.raises(ValueError), db.transaction():
        db.execute("INSERT INTO settings (key, value) VALUES ('b', '1')")
        raise ValueError
    assert db.fetch_one("SELECT 1 FROM settings WHERE key = 'b'") is None


def test_nested_transaction_joins_outer(ctx):
    with pytest.raises(ValueError), db.transaction():
        with db.transaction():
            db.execute("INSERT INTO settings (key, value) VALUES ('c', '1')")
        raise ValueError
    assert db.fetch_one("SELECT 1 FROM settings WHERE key = 'c'") is None
