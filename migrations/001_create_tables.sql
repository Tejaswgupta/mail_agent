-- Migration 001: create mail agent tables

CREATE TABLE IF NOT EXISTS processed_emails (
    email_id    TEXT PRIMARY KEY,
    subject     TEXT,
    sender      TEXT,
    received_at TEXT,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS attachments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id     TEXT NOT NULL REFERENCES processed_emails(email_id) ON DELETE CASCADE,
    file_name    TEXT NOT NULL,
    file_size    BIGINT NOT NULL,
    sha256       TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS attachments_email_id_idx ON attachments(email_id);
CREATE INDEX IF NOT EXISTS attachments_sha256_idx   ON attachments(sha256);

CREATE TABLE IF NOT EXISTS agent_heartbeat (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    heartbeat_time TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
