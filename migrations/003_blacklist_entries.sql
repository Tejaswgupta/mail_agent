-- Migration 003: client blacklist records for manifest matching

CREATE TABLE IF NOT EXISTS blacklist_entries (
    id          TEXT PRIMARY KEY,
    passport    TEXT,
    mobile_no   TEXT,
    email_id    TEXT,
    name        TEXT,
    notes       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS blacklist_passport_idx  ON blacklist_entries(passport);
CREATE INDEX IF NOT EXISTS blacklist_mobile_no_idx ON blacklist_entries(mobile_no);
CREATE INDEX IF NOT EXISTS blacklist_email_id_idx  ON blacklist_entries(email_id);
CREATE INDEX IF NOT EXISTS blacklist_name_idx      ON blacklist_entries(name);

CREATE INDEX IF NOT EXISTS manifest_pax_passport_idx ON manifest_passengers(passport_number);
