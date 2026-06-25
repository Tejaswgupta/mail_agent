"""SQLite storage — schema creation, email dedup, attachment records, parsed data."""

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
            CREATE INDEX IF NOT EXISTS manifest_pax_passport_idx   ON manifest_passengers(passport_number);

            WITH ranked_manifest_duplicates AS (
                SELECT
                    mp.id,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            lower(trim(mp.pnr)),
                            mp.flight_date,
                            lower(trim(COALESCE(
                                NULLIF(mp.full_name, ''),
                                trim(COALESCE(mp.first_name, '') || ' ' || COALESCE(mp.last_name, ''))
                            )))
                        ORDER BY COALESCE(a.uploaded_at, '') DESC, mp.rowid DESC
                    ) AS duplicate_rank
                FROM manifest_passengers mp
                LEFT JOIN attachments a ON a.id = mp.attachment_id
                WHERE mp.pnr IS NOT NULL
                  AND trim(mp.pnr) <> ''
                  AND mp.flight_date IS NOT NULL
                  AND trim(mp.flight_date) <> ''
                  AND trim(COALESCE(
                        NULLIF(mp.full_name, ''),
                        trim(COALESCE(mp.first_name, '') || ' ' || COALESCE(mp.last_name, ''))
                  )) <> ''
            )
            DELETE FROM manifest_passengers
            WHERE id IN (
                SELECT id FROM ranked_manifest_duplicates WHERE duplicate_rank > 1
            );

            CREATE UNIQUE INDEX IF NOT EXISTS manifest_pax_unique_pnr_date_name_idx
            ON manifest_passengers (
                lower(trim(pnr)),
                flight_date,
                lower(trim(COALESCE(
                    NULLIF(full_name, ''),
                    trim(COALESCE(first_name, '') || ' ' || COALESCE(last_name, ''))
                )))
            )
            WHERE pnr IS NOT NULL
              AND trim(pnr) <> ''
              AND flight_date IS NOT NULL
              AND trim(flight_date) <> ''
              AND trim(COALESCE(
                    NULLIF(full_name, ''),
                    trim(COALESCE(first_name, '') || ' ' || COALESCE(last_name, ''))
              )) <> '';

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
            """INSERT OR REPLACE INTO manifest_passengers
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


# ── Client interface queries ─────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _norm_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _phone_matches(left: Any, right: Any) -> bool:
    left_digits = _norm_phone(left)
    right_digits = _norm_phone(right)
    if not left_digits or not right_digits:
        return False
    if left_digits == right_digits:
        return True
    shorter, longer = sorted((left_digits, right_digits), key=len)
    return len(shorter) >= 7 and longer.endswith(shorter)


def _passenger_name(row: dict[str, Any]) -> str:
    if row.get("full_name"):
        return str(row["full_name"]).strip()
    return " ".join(
        part for part in (
            str(row.get("first_name") or "").strip(),
            str(row.get("last_name") or "").strip(),
        )
        if part
    )


def list_blacklist_entries() -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            """SELECT id, passport, mobile_no, email_id, name, notes, created_at, updated_at
               FROM blacklist_entries
               ORDER BY updated_at DESC, created_at DESC"""
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def upsert_blacklist_entry(
    *,
    entry_id: str | None = None,
    passport: str | None = None,
    mobile_no: str | None = None,
    email_id: str | None = None,
    name: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Create or update one blacklist entry."""
    values = {
        "passport": _clean_text(passport),
        "mobile_no": _clean_text(mobile_no),
        "email_id": _clean_text(email_id),
        "name": _clean_text(name),
        "notes": _clean_text(notes),
    }
    if not any(values[field] for field in ("passport", "mobile_no", "email_id", "name")):
        raise ValueError("At least one of passport, mobile_no, email_id, or name is required")

    now = _now()
    with _conn() as con:
        if entry_id:
            existing = con.execute(
                "SELECT id FROM blacklist_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if existing is None:
                raise KeyError(f"Blacklist entry not found: {entry_id}")
            con.execute(
                """UPDATE blacklist_entries
                   SET passport = ?, mobile_no = ?, email_id = ?, name = ?,
                       notes = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    values["passport"], values["mobile_no"], values["email_id"],
                    values["name"], values["notes"], now, entry_id,
                ),
            )
            row_id = entry_id
        else:
            row_id = str(uuid.uuid4())
            con.execute(
                """INSERT INTO blacklist_entries
                   (id, passport, mobile_no, email_id, name, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row_id, values["passport"], values["mobile_no"], values["email_id"],
                    values["name"], values["notes"], now, now,
                ),
            )
        row = con.execute(
            """SELECT id, passport, mobile_no, email_id, name, notes, created_at, updated_at
               FROM blacklist_entries WHERE id = ?""",
            (row_id,),
        ).fetchone()
    return _row_to_dict(row)


def delete_blacklist_entry(entry_id: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM blacklist_entries WHERE id = ?", (entry_id,))
    return cur.rowcount > 0


def _manifest_select_sql(where_sql: str = "") -> str:
    return f"""
        SELECT
            mp.id, mp.attachment_id, mp.airline_code, mp.manifest_type,
            mp.flight_number, mp.flight_date, mp.origin, mp.destination, mp.pnr,
            mp.title, mp.first_name, mp.last_name, mp.full_name, mp.passenger_type,
            mp.gender, mp.date_of_birth, mp.nationality, mp.passport_number,
            mp.cabin_class, mp.seat_number, mp.no_of_bags, mp.baggage_weight,
            mp.ticket_number, mp.ticket_issue_date, mp.booking_date, mp.payment_mode,
            mp.phone, mp.email, mp.raw_data,
            a.file_name AS attachment_file_name,
            a.uploaded_at AS attachment_uploaded_at,
            pe.subject AS email_subject,
            pe.sender AS email_sender,
            pe.received_at AS email_received_at
        FROM manifest_passengers mp
        LEFT JOIN attachments a ON a.id = mp.attachment_id
        LEFT JOIN processed_emails pe ON pe.email_id = a.email_id
        {where_sql}
    """


def list_manifest_passengers(
    *,
    query: str | None = None,
    flight_date: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if flight_date:
        clauses.append("mp.flight_date = ?")
        params.append(flight_date)
    if query:
        like = f"%{query.strip()}%"
        clauses.append(
            """(
                mp.passport_number LIKE ? OR mp.full_name LIKE ? OR mp.first_name LIKE ?
                OR mp.last_name LIKE ? OR mp.phone LIKE ? OR mp.email LIKE ?
                OR mp.pnr LIKE ? OR mp.flight_number LIKE ?
            )"""
        )
        params.extend([like] * 8)
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    sql = _manifest_select_sql(where_sql) + """
        ORDER BY COALESCE(mp.flight_date, '') DESC, mp.flight_number, mp.full_name, mp.last_name
        LIMIT ?
    """
    params.append(max(1, min(limit, 2000)))
    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [_row_to_dict(row) | {"display_name": _passenger_name(_row_to_dict(row))} for row in rows]


def passenger_history_by_passport(passport: str) -> list[dict[str, Any]]:
    passport = passport.strip()
    if not passport:
        return []
    sql = _manifest_select_sql("WHERE lower(trim(mp.passport_number)) = lower(trim(?))") + """
        ORDER BY COALESCE(mp.flight_date, '') DESC, mp.flight_number, mp.pnr
    """
    with _conn() as con:
        rows = con.execute(sql, (passport,)).fetchall()
    return [_row_to_dict(row) | {"display_name": _passenger_name(_row_to_dict(row))} for row in rows]


def active_blacklist_alerts(days: int | None = None) -> list[dict[str, Any]]:
    """Return manifest passengers matching blacklist records, grouped by flight day in the UI."""
    where_sql = ""
    params: list[Any] = []
    if days is not None and days > 0:
        where_sql = "WHERE mp.flight_date >= date('now', ?)"
        params.append(f"-{int(days)} days")

    with _conn() as con:
        passengers = [
            _row_to_dict(row)
            for row in con.execute(
                _manifest_select_sql(where_sql)
                + " ORDER BY COALESCE(mp.flight_date, '') DESC, mp.flight_number, mp.full_name",
                params,
            ).fetchall()
        ]
        blacklist = [
            _row_to_dict(row)
            for row in con.execute(
                """SELECT id, passport, mobile_no, email_id, name, notes, created_at, updated_at
                   FROM blacklist_entries"""
            ).fetchall()
        ]

    alerts: list[dict[str, Any]] = []
    for passenger in passengers:
        passenger_display_name = _passenger_name(passenger)
        for entry in blacklist:
            matched_fields: list[str] = []
            if entry.get("passport") and _norm(entry["passport"]) == _norm(passenger.get("passport_number")):
                matched_fields.append("passport")
            if entry.get("mobile_no") and _phone_matches(entry["mobile_no"], passenger.get("phone")):
                matched_fields.append("mobile_no")
            if entry.get("email_id") and _norm(entry["email_id"]) == _norm(passenger.get("email")):
                matched_fields.append("email_id")
            if entry.get("name") and _norm(entry["name"]) == _norm(passenger_display_name):
                matched_fields.append("name")
            if matched_fields:
                alerts.append(
                    {
                        "day": passenger.get("flight_date") or "Unknown date",
                        "matched_fields": matched_fields,
                        "passenger": passenger | {"display_name": passenger_display_name},
                        "blacklist": entry,
                    }
                )
    return alerts


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
