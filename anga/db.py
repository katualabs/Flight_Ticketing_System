"""SQLite access: per-request connections, transactions and migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, current_app, g

from anga import clock

PACKAGE_DIR = Path(__file__).parent
SCHEMA_FILE = PACKAGE_DIR / "schema.sql"
MIGRATIONS_DIR = PACKAGE_DIR / "migrations"
BASELINE_VERSION = "0000_schema"


def connect(path: str) -> sqlite3.Connection:
    """Open a connection configured the way the whole app expects.

    ``isolation_level=None`` turns off the driver's implicit transactions, so a
    transaction exists only where ``transaction()`` says it does.
    """
    conn = sqlite3.connect(path, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_exc: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Run a block atomically, taking the write lock up front.

    ``BEGIN IMMEDIATE`` makes concurrent writers queue at the start rather than
    fail halfway with a lock upgrade error, which is what keeps guarded
    inventory updates simple. Nested use joins the outer transaction so
    services can compose without knowing who called them.
    """
    conn = get_db()
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def fetch_one(sql: str, params: Sequence | dict = ()) -> sqlite3.Row | None:
    return get_db().execute(sql, params).fetchone()


def fetch_all(sql: str, params: Sequence | dict = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def fetch_value(sql: str, params: Sequence | dict = ()):
    row = get_db().execute(sql, params).fetchone()
    return row[0] if row else None


def execute(sql: str, params: Sequence | dict = ()) -> sqlite3.Cursor:
    return get_db().execute(sql, params)


def execute_many(sql: str, rows: Iterable[Sequence]) -> None:
    get_db().executemany(sql, rows)


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply the baseline schema and any numbered migrations not yet applied.

    Returns the versions applied, oldest first. Each one runs in its own
    transaction so a failed migration leaves the database at the previous
    version rather than half upgraded.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    pending = [(BASELINE_VERSION, SCHEMA_FILE)]
    if MIGRATIONS_DIR.exists():
        pending += [(path.stem, path) for path in sorted(MIGRATIONS_DIR.glob("*.sql"))]

    done = []
    for version, path in pending:
        if version in applied:
            continue
        _apply_script(conn, version, path.read_text(encoding="utf-8"))
        done.append(version)
    return done


def _apply_script(conn: sqlite3.Connection, version: str, sql: str) -> None:
    # executescript() issues its own COMMIT first, so the statements are wrapped
    # in the script itself to stay atomic.
    stamp = clock.timestamp().replace("'", "")
    script = (
        f"BEGIN;\n{sql}\n"
        f"INSERT INTO schema_migrations (version, applied_at) VALUES ('{version}', '{stamp}');\n"
        "COMMIT;"
    )
    try:
        conn.executescript(script)
    except sqlite3.Error:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def init_db() -> list[str]:
    """Bring the configured database up to the latest schema."""
    return run_migrations(get_db())


def init_app(app: Flask) -> None:
    app.teardown_appcontext(close_db)
