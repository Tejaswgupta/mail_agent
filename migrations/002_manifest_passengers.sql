-- Migration 002: normalized passenger manifest table (all carriers: 6E / IX / TG)

CREATE TABLE IF NOT EXISTS manifest_passengers (
    id                TEXT PRIMARY KEY,
    attachment_id     TEXT NOT NULL REFERENCES attachments(id),
    airline_code      TEXT NOT NULL,
    manifest_type     TEXT NOT NULL,   -- pre_departure | post_departure
    flight_number     TEXT,
    flight_date       TEXT,
    origin            TEXT,
    destination       TEXT,
    pnr               TEXT,
    title             TEXT,
    first_name        TEXT,
    last_name         TEXT,
    full_name         TEXT,
    passenger_type    TEXT,
    gender            TEXT,
    date_of_birth     TEXT,
    nationality       TEXT,
    passport_number   TEXT,
    cabin_class       TEXT,
    seat_number       TEXT,
    no_of_bags        INTEGER,
    baggage_weight    TEXT,
    ticket_number     TEXT,
    ticket_issue_date TEXT,
    booking_date      TEXT,
    payment_mode      TEXT,
    phone             TEXT,
    email             TEXT,
    raw_data          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS manifest_pax_attachment_idx ON manifest_passengers(attachment_id);
CREATE INDEX IF NOT EXISTS manifest_pax_flight_idx     ON manifest_passengers(flight_number, flight_date);
CREATE INDEX IF NOT EXISTS manifest_pax_pnr_idx        ON manifest_passengers(pnr);
