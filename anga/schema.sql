-- Anga Air baseline schema. Later changes are numbered files in migrations/.
-- Money is always INTEGER Kenyan shillings; timestamps are ISO-8601 network time.

CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE airports (
    code       TEXT PRIMARY KEY CHECK (length(code) = 3),
    city       TEXT NOT NULL,
    name       TEXT NOT NULL,
    country    TEXT NOT NULL,
    timezone   TEXT NOT NULL,
    lat        REAL NOT NULL,
    lng        REAL NOT NULL,
    is_coastal INTEGER NOT NULL DEFAULT 0 CHECK (is_coastal IN (0, 1))
);

CREATE TABLE aircraft_types (
    code   TEXT PRIMARY KEY,
    name   TEXT NOT NULL,
    layout TEXT NOT NULL CHECK (json_valid(layout))
);

-- Templates the rolling schedule is generated from. Weekdays use Monday = 1.
CREATE TABLE route_schedules (
    flight_number    TEXT PRIMARY KEY,
    origin           TEXT NOT NULL REFERENCES airports (code),
    destination      TEXT NOT NULL REFERENCES airports (code),
    departure_time   TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    aircraft_code    TEXT NOT NULL REFERENCES aircraft_types (code),
    base_fare        INTEGER NOT NULL CHECK (base_fare > 0),
    weekdays         TEXT NOT NULL DEFAULT '1234567',
    active           INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    CHECK (origin <> destination)
);

CREATE TABLE flights (
    id               INTEGER PRIMARY KEY,
    flight_number    TEXT NOT NULL,
    departure_date   TEXT NOT NULL,
    origin           TEXT NOT NULL REFERENCES airports (code),
    destination      TEXT NOT NULL REFERENCES airports (code),
    departure_time   TEXT NOT NULL,
    arrival_time     TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    aircraft_code    TEXT NOT NULL REFERENCES aircraft_types (code),
    status           TEXT NOT NULL DEFAULT 'Scheduled' CHECK (status IN
        ('Scheduled', 'On time', 'Delayed', 'Boarding', 'Departed', 'Landed', 'Cancelled')),
    delay_minutes    INTEGER NOT NULL DEFAULT 0 CHECK (delay_minutes >= 0),
    gate             TEXT,
    UNIQUE (flight_number, departure_date),
    CHECK (origin <> destination)
);
CREATE INDEX idx_flights_route_date ON flights (origin, destination, departure_date);
CREATE INDEX idx_flights_date ON flights (departure_date);

-- A cabin's seats are partitioned between its fare families, so the buckets of
-- one cabin always add up to the seats physically in it.
CREATE TABLE fares (
    id              INTEGER PRIMARY KEY,
    flight_id       INTEGER NOT NULL REFERENCES flights (id) ON DELETE CASCADE,
    cabin           TEXT NOT NULL CHECK (cabin IN ('Economy', 'Business', 'First')),
    fare_family     TEXT NOT NULL CHECK (fare_family IN ('Lite', 'Classic', 'Flex')),
    price           INTEGER NOT NULL CHECK (price > 0),
    total_seats     INTEGER NOT NULL CHECK (total_seats >= 0),
    available_seats INTEGER NOT NULL CHECK (available_seats >= 0),
    CHECK (available_seats <= total_seats),
    UNIQUE (flight_id, cabin, fare_family)
);

CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    full_name     TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone         TEXT,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'agent', 'admin')),
    miles_balance INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    last_login    TEXT
);

CREATE TABLE saved_travellers (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    full_name     TEXT NOT NULL,
    id_number     TEXT NOT NULL,
    date_of_birth TEXT
);
CREATE INDEX idx_saved_travellers_user ON saved_travellers (user_id);

CREATE TABLE promo_codes (
    id         INTEGER PRIMARY KEY,
    code       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    kind       TEXT NOT NULL CHECK (kind IN ('percent', 'fixed')),
    value      INTEGER NOT NULL CHECK (value > 0),
    scope      TEXT NOT NULL DEFAULT 'all' CHECK (scope IN ('all', 'coastal')),
    min_spend  INTEGER NOT NULL DEFAULT 0 CHECK (min_spend >= 0),
    valid_from TEXT NOT NULL,
    valid_to   TEXT NOT NULL,
    max_uses   INTEGER CHECK (max_uses IS NULL OR max_uses > 0),
    used_count INTEGER NOT NULL DEFAULT 0 CHECK (used_count >= 0),
    active     INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    CHECK (kind <> 'percent' OR value <= 100),
    CHECK (valid_from <= valid_to)
);

CREATE TABLE bookings (
    id              INTEGER PRIMARY KEY,
    reference       TEXT NOT NULL UNIQUE,
    user_id         INTEGER REFERENCES users (id) ON DELETE SET NULL,
    contact_email   TEXT NOT NULL,
    contact_phone   TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('Pending', 'Confirmed', 'Cancelled')),
    trip_type       TEXT NOT NULL CHECK (trip_type IN ('one_way', 'round_trip')),
    subtotal        INTEGER NOT NULL CHECK (subtotal >= 0),
    seats_total     INTEGER NOT NULL DEFAULT 0 CHECK (seats_total >= 0),
    extras_total    INTEGER NOT NULL DEFAULT 0 CHECK (extras_total >= 0),
    discount        INTEGER NOT NULL DEFAULT 0 CHECK (discount >= 0),
    changes_total   INTEGER NOT NULL DEFAULT 0 CHECK (changes_total >= 0),
    total           INTEGER NOT NULL CHECK (total >= 0),
    currency        TEXT NOT NULL DEFAULT 'KES',
    promo_id        INTEGER REFERENCES promo_codes (id),
    needs_rebooking INTEGER NOT NULL DEFAULT 0 CHECK (needs_rebooking IN (0, 1)),
    created_at      TEXT NOT NULL,
    expires_at      TEXT,
    cancelled_at    TEXT
);
CREATE INDEX idx_bookings_user ON bookings (user_id);
CREATE INDEX idx_bookings_status_expiry ON bookings (status, expires_at);
CREATE INDEX idx_bookings_created ON bookings (created_at);

CREATE TABLE booking_segments (
    id          INTEGER PRIMARY KEY,
    booking_id  INTEGER NOT NULL REFERENCES bookings (id) ON DELETE CASCADE,
    flight_id   INTEGER NOT NULL REFERENCES flights (id) ON DELETE RESTRICT,
    cabin       TEXT NOT NULL CHECK (cabin IN ('Economy', 'Business', 'First')),
    fare_family TEXT NOT NULL CHECK (fare_family IN ('Lite', 'Classic', 'Flex')),
    direction   TEXT NOT NULL CHECK (direction IN ('outbound', 'return')),
    fare_paid   INTEGER NOT NULL DEFAULT 0 CHECK (fare_paid >= 0),
    UNIQUE (booking_id, direction)
);
CREATE INDEX idx_segments_flight ON booking_segments (flight_id);

CREATE TABLE booking_passengers (
    id             INTEGER PRIMARY KEY,
    booking_id     INTEGER NOT NULL REFERENCES bookings (id) ON DELETE CASCADE,
    full_name      TEXT NOT NULL,
    id_number      TEXT NOT NULL,
    date_of_birth  TEXT,
    passenger_type TEXT NOT NULL CHECK (passenger_type IN ('adult', 'child', 'infant'))
);
CREATE INDEX idx_passengers_booking ON booking_passengers (booking_id);

CREATE TABLE seats (
    id                   INTEGER PRIMARY KEY,
    flight_id            INTEGER NOT NULL REFERENCES flights (id) ON DELETE CASCADE,
    seat_code            TEXT NOT NULL,
    cabin                TEXT NOT NULL CHECK (cabin IN ('Economy', 'Business', 'First')),
    is_window            INTEGER NOT NULL DEFAULT 0,
    is_aisle             INTEGER NOT NULL DEFAULT 0,
    extra_legroom        INTEGER NOT NULL DEFAULT 0,
    price_extra          INTEGER NOT NULL DEFAULT 0 CHECK (price_extra >= 0),
    blocked              INTEGER NOT NULL DEFAULT 0,
    booking_passenger_id INTEGER REFERENCES booking_passengers (id) ON DELETE SET NULL,
    UNIQUE (flight_id, seat_code)
);
CREATE INDEX idx_seats_passenger ON seats (booking_passenger_id);

-- One row per passenger per segment. Check-in state lives here rather than on
-- the passenger because each leg of a round trip is checked in separately.
-- seat_id is NULL for infants, who travel on a lap.
CREATE TABLE passenger_seats (
    id                   INTEGER PRIMARY KEY,
    booking_passenger_id INTEGER NOT NULL REFERENCES booking_passengers (id) ON DELETE CASCADE,
    segment_id           INTEGER NOT NULL REFERENCES booking_segments (id) ON DELETE CASCADE,
    seat_id              INTEGER REFERENCES seats (id),
    seat_price_paid      INTEGER NOT NULL DEFAULT 0,
    checked_in_at        TEXT,
    boarding_sequence    INTEGER,
    boarding_group       INTEGER,
    UNIQUE (booking_passenger_id, segment_id)
);
CREATE INDEX idx_passenger_seats_segment ON passenger_seats (segment_id);

CREATE TABLE extras (
    code   TEXT PRIMARY KEY,
    name   TEXT NOT NULL,
    price  INTEGER NOT NULL CHECK (price >= 0),
    type   TEXT NOT NULL CHECK (type IN ('bag', 'meal', 'priority', 'lounge')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE booking_extras (
    id                   INTEGER PRIMARY KEY,
    booking_id           INTEGER NOT NULL REFERENCES bookings (id) ON DELETE CASCADE,
    booking_passenger_id INTEGER NOT NULL REFERENCES booking_passengers (id) ON DELETE CASCADE,
    extra_code           TEXT NOT NULL REFERENCES extras (code),
    quantity             INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    line_total           INTEGER NOT NULL CHECK (line_total >= 0)
);
CREATE INDEX idx_booking_extras_booking ON booking_extras (booking_id);

-- Refunds are positive amounts with kind 'refund', so history stays append-only
-- and net revenue is charges minus refunds.
CREATE TABLE payments (
    id          INTEGER PRIMARY KEY,
    booking_id  INTEGER NOT NULL REFERENCES bookings (id) ON DELETE CASCADE,
    method      TEXT NOT NULL CHECK (method IN ('mpesa', 'card_sim', 'pay_later')),
    kind        TEXT NOT NULL DEFAULT 'charge' CHECK (kind IN ('charge', 'refund')),
    amount      INTEGER NOT NULL CHECK (amount >= 0),
    status      TEXT NOT NULL CHECK (status IN ('initiated', 'succeeded', 'failed')),
    reference   TEXT NOT NULL UNIQUE,
    phone       TEXT,
    card_last4  TEXT CHECK (card_last4 IS NULL OR length(card_last4) = 4),
    created_at  TEXT NOT NULL,
    settles_at  TEXT
);
CREATE INDEX idx_payments_booking ON payments (booking_id);
CREATE INDEX idx_payments_created ON payments (created_at);

CREATE TABLE miles_ledger (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    booking_id INTEGER REFERENCES bookings (id) ON DELETE SET NULL,
    delta      INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_miles_user ON miles_ledger (user_id);

CREATE TABLE contact_messages (
    id         INTEGER PRIMARY KEY,
    full_name  TEXT NOT NULL,
    email      TEXT NOT NULL,
    subject    TEXT NOT NULL,
    body       TEXT NOT NULL,
    is_read    INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    reply_note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE outbox (
    id         INTEGER PRIMARY KEY,
    recipient  TEXT NOT NULL,
    subject    TEXT NOT NULL,
    html_body  TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_outbox_created ON outbox (created_at);

CREATE TABLE audit_log (
    id            INTEGER PRIMARY KEY,
    actor_user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    action        TEXT NOT NULL,
    entity        TEXT NOT NULL,
    entity_id     TEXT,
    details       TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(details)),
    created_at    TEXT NOT NULL
);
CREATE INDEX idx_audit_created ON audit_log (created_at);
CREATE INDEX idx_audit_action ON audit_log (action);

-- Wizard state is kept server-side: a signed cookie is too small for nine
-- passengers, and passenger ID numbers should not travel to the browser.
CREATE TABLE booking_drafts (
    token      TEXT PRIMARY KEY,
    data       TEXT NOT NULL CHECK (json_valid(data)),
    updated_at TEXT NOT NULL
);
