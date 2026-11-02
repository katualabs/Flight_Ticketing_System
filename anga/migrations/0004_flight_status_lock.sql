-- Once staff set a flight's status by hand, the simulated clock must leave it alone.
ALTER TABLE flights ADD COLUMN status_locked INTEGER NOT NULL DEFAULT 0
    CHECK (status_locked IN (0, 1));
