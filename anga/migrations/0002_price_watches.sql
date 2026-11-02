-- Price-drop watches: a customer's saved route and date, and the fare they saw.
CREATE TABLE price_watches (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    origin        TEXT NOT NULL REFERENCES airports (code),
    destination   TEXT NOT NULL REFERENCES airports (code),
    travel_date   TEXT NOT NULL,
    cabin         TEXT NOT NULL DEFAULT 'Economy',
    seen_price    INTEGER NOT NULL CHECK (seen_price > 0),
    alert_price   INTEGER,
    alerted_at    TEXT,
    dismissed     INTEGER NOT NULL DEFAULT 0 CHECK (dismissed IN (0, 1)),
    created_at    TEXT NOT NULL,
    UNIQUE (user_id, origin, destination, travel_date, cabin)
);
CREATE INDEX idx_price_watches_user ON price_watches (user_id);
