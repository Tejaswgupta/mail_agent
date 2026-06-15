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

            -- Each row from an xlsx sheet
            CREATE TABLE IF NOT EXISTS xlsx_rows (
                id           TEXT PRIMARY KEY,
                attachment_id TEXT NOT NULL REFERENCES attachments(id),
                sheet_name   TEXT NOT NULL,
                row_index    INTEGER NOT NULL,
                data         TEXT NOT NULL    -- JSON object keyed by column header
            );

            CREATE INDEX IF NOT EXISTS xlsx_rows_attachment_idx ON xlsx_rows(attachment_id);

            -- Each table extracted from a PDF page
            CREATE TABLE IF NOT EXISTS pdf_tables (
                id           TEXT PRIMARY KEY,
                attachment_id TEXT NOT NULL REFERENCES attachments(id),
                page_number  INTEGER NOT NULL,
                table_index  INTEGER NOT NULL,
                headers      TEXT NOT NULL,   -- JSON array of column names
                rows         TEXT NOT NULL    -- JSON array of arrays (row data)
            );

            CREATE INDEX IF NOT EXISTS pdf_tables_attachment_idx ON pdf_tables(attachment_id);

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

def store_xlsx_rows(attachment_id: str, sheet_name: str, rows: list[dict[str, Any]]) -> int:
    """Bulk-insert parsed xlsx rows. Returns count inserted."""
    if not rows:
        return 0
    with _conn() as con:
        con.executemany(
            """INSERT INTO xlsx_rows (id, attachment_id, sheet_name, row_index, data)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (str(uuid.uuid4()), attachment_id, sheet_name, i, json.dumps(row, default=str))
                for i, row in enumerate(rows)
            ],
        )
    logger.info(f"Stored {len(rows)} xlsx row(s) from sheet '{sheet_name}' for attachment {attachment_id}")
    return len(rows)


def store_pdf_tables(
    attachment_id: str,
    page_number: int,
    table_index: int,
    headers: list[str],
    rows: list[list[Any]],
) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO pdf_tables
               (id, attachment_id, page_number, table_index, headers, rows)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                attachment_id,
                page_number,
                table_index,
                json.dumps(headers, default=str),
                json.dumps(rows, default=str),
            ),
        )
    logger.info(f"Stored PDF table p{page_number}[{table_index}] for attachment {attachment_id}")


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
