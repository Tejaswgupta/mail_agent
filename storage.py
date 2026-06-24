"""SQLite storage — schema creation, email dedup, attachment records, parsed data."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings

# ── Connection ───────────────────────────────────────────────────────────────

@contextmanager
def _conn():
    con = sqlite3.connect(str(settings.DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")   # safe for concurrent readers
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Schema bootstrap (idempotent) ────────────────────────────────────────────

def init_db() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS processed_emails (
                email_id     TEXT PRIMARY KEY,
                subject      TEXT,
                sender       TEXT,
                received_at  TEXT,
                processed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attachments (
                id           TEXT PRIMARY KEY,
                email_id     TEXT NOT NULL REFERENCES processed_emails(email_id),
                file_name    TEXT NOT NULL,
                file_size    INTEGER NOT NULL,
                sha256       TEXT NOT NULL,
                local_path   TEXT NOT NULL,
                uploaded_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS attachments_email_id_idx ON attachments(email_id);
            CREATE INDEX IF NOT EXISTS attachments_sha256_idx   ON attachments(sha256);

            -- Normalized passenger manifest rows (all carriers)
            CREATE TABLE IF NOT EXISTS manifest_passengers (
                id              TEXT PRIMARY KEY,
                attachment_id   TEXT NOT NULL REFERENCES attachments(id),
                airline_code    TEXT NOT NULL,   -- 6E / IX / TG
                manifest_type   TEXT NOT NULL,   -- pre_departure / post_departure
                flight_number   TEXT,
                flight_date     TEXT,
                origin          TEXT,
                destination     TEXT,
                pnr             TEXT,
                title           TEXT,
                first_name      TEXT,
                last_name       TEXT,
                full_name       TEXT,
                passenger_type  TEXT,
                gender          TEXT,
                date_of_birth   TEXT,
                nationality     TEXT,
                passport_number TEXT,
                cabin_class     TEXT,
                seat_number     TEXT,
                no_of_bags      INTEGER,
                baggage_weight  TEXT,
                ticket_number   TEXT,
                ticket_issue_date TEXT,
                booking_date    TEXT,
                payment_mode    TEXT,
                phone           TEXT,
                email           TEXT,
                raw_data        TEXT NOT NULL    -- JSON of original source row
            );

            CREATE INDEX IF NOT EXISTS manifest_pax_attachment_idx ON manifest_passengers(attachment_id);
            CREATE INDEX IF NOT EXISTS manifest_pax_flight_idx     ON manifest_passengers(flight_number, flight_date);
            CREATE INDEX IF NOT EXISTS manifest_pax_pnr_idx        ON manifest_passengers(pnr);

            CREATE TABLE IF NOT EXISTS agent_heartbeat (
                id             TEXT PRIMARY KEY,
                heartbeat_time TEXT NOT NULL
            );
        """)
    logger.info(f"Database ready: {settings.DB_PATH}")


# ── Email dedup ───────────────────────────────────────────────────────────────

def is_processed(email_id: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM processed_emails WHERE email_id = ?", (email_id,)
        ).fetchone()
    return row is not None


def mark_processed(email_id: str, subject: str, sender: str, received_at: str) -> None:
    with _conn() as con:
        con.execute(
            """INSERT OR REPLACE INTO processed_emails
               (email_id, subject, sender, received_at, processed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (email_id, subject, sender, received_at, _now()),
        )
    logger.info(f"Marked email {email_id} as processed")


# ── Attachment record ─────────────────────────────────────────────────────────

def record_attachment(
    email_id: str,
    file_name: str,
    file_size: int,
    sha256: str,
    local_path: str,
) -> str:
    """Insert attachment row, return its UUID."""
    aid = str(uuid.uuid4())
    with _conn() as con:
        con.execute(
            """INSERT INTO attachments
               (id, email_id, file_name, file_size, sha256, local_path, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (aid, email_id, file_name, file_size, sha256, local_path, _now()),
        )
    logger.info(f"Recorded attachment {file_name} (id={aid})")
    return aid


# ── Parsed data storage ───────────────────────────────────────────────────────

# ── Passenger manifests ──────────────────────────────────────────────────────

def store_manifest_passengers(
    attachment_id: str,
    airline_code: str,
    manifest_type: str,
    rows: list[dict[str, Any]],
) -> int:
    """Bulk-insert normalized manifest rows. Returns count inserted."""
    if not rows:
        return 0

    _TEXT_COLS = {
        "flight_number", "flight_date", "origin", "destination", "pnr",
        "title", "first_name", "last_name", "full_name", "passenger_type",
        "gender", "date_of_birth", "nationality", "passport_number",
        "cabin_class", "seat_number", "baggage_weight", "ticket_number",
        "ticket_issue_date", "booking_date", "payment_mode", "phone", "email",
    }

    def _val(row: dict, col: str) -> Any:
        v = row.get(col)
        if col == "no_of_bags" and v is not None:
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return None
        if col in _TEXT_COLS:
            return str(v).strip() if v is not None and v != "" else None
        return v

    with _conn() as con:
        con.executemany(
            """INSERT INTO manifest_passengers
               (id, attachment_id, airline_code, manifest_type,
                flight_number, flight_date, origin, destination, pnr,
                title, first_name, last_name, full_name,
                passenger_type, gender, date_of_birth, nationality, passport_number,
                cabin_class, seat_number, no_of_bags, baggage_weight,
                ticket_number, ticket_issue_date, booking_date,
                payment_mode, phone, email, raw_data)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    str(uuid.uuid4()), attachment_id, airline_code, manifest_type,
                    _val(r, "flight_number"), _val(r, "flight_date"),
                    _val(r, "origin"), _val(r, "destination"), _val(r, "pnr"),
                    _val(r, "title"), _val(r, "first_name"), _val(r, "last_name"),
                    _val(r, "full_name"), _val(r, "passenger_type"), _val(r, "gender"),
                    _val(r, "date_of_birth"), _val(r, "nationality"), _val(r, "passport_number"),
                    _val(r, "cabin_class"), _val(r, "seat_number"), _val(r, "no_of_bags"),
                    _val(r, "baggage_weight"), _val(r, "ticket_number"),
                    _val(r, "ticket_issue_date"), _val(r, "booking_date"),
                    _val(r, "payment_mode"), _val(r, "phone"), _val(r, "email"),
                    json.dumps(r.get("_raw", {}), default=str),
                )
                for r in rows
            ],
        )
    logger.info(
        f"Stored {len(rows)} manifest passenger(s) [{airline_code}/{manifest_type}] "
        f"for attachment {attachment_id}"
    )
    return len(rows)


# ── Reset ────────────────────────────────────────────────────────────────────

def reset_processed_emails() -> int:
    """Delete all rows from processed_emails (and their attachments/passengers via cascade).
    Returns the number of emails deleted."""
    with _conn() as con:
        count = con.execute("SELECT COUNT(*) FROM processed_emails").fetchone()[0]
        con.executescript("""
            DELETE FROM manifest_passengers;
            DELETE FROM attachments;
            DELETE FROM processed_emails;
        """)
    logger.warning(f"Reset: deleted {count} processed email(s) and all related records")
    return count


# ── Heartbeat ─────────────────────────────────────────────────────────────────

def heartbeat() -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO agent_heartbeat (id, heartbeat_time) VALUES (?, ?)",
            (str(uuid.uuid4()), _now()),
        )


# ── Helper ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
