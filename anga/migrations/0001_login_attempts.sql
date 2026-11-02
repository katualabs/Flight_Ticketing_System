-- Failed sign-ins are counted in the database rather than in memory so a lockout
-- holds across gunicorn workers and restarts.
CREATE TABLE login_attempts (
    email        TEXT PRIMARY KEY COLLATE NOCASE,
    failures     INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT
);
