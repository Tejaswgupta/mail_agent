"""Tests for storage.py — uses an isolated SQLite DB per test (via conftest)."""
import storage


def test_is_processed_false_for_new_email():
    assert storage.is_processed("new-email-id") is False


def test_mark_and_is_processed():
    storage.mark_processed("e1", "Subject", "sender@test.com", "2024-01-01T00:00:00")
    assert storage.is_processed("e1") is True


def test_mark_processed_idempotent():
    storage.mark_processed("e2", "S", "a@b.com", "2024-01-01")
    storage.mark_processed("e2", "S updated", "a@b.com", "2024-01-01")  # INSERT OR REPLACE
    assert storage.is_processed("e2") is True


def test_record_attachment_returns_id():
    storage.mark_processed("e3", "S", "a@b.com", "2024-01-01")
    aid = storage.record_attachment(
        email_id="e3",
        file_name="invoice.pdf",
        file_size=2048,
        sha256="a" * 64,
        local_path="/downloads/invoice.pdf",
    )
    assert isinstance(aid, str) and len(aid) == 36  # UUID


def test_store_manifest_passengers_count():
    storage.mark_processed("e4", "S", "a@b.com", "2024-01-01")
    aid = storage.record_attachment("e4", "6E1401.xlsx", 512, "b" * 64, "/d/6E1401.xlsx")
    rows = [
        {"flight_number": "6E-1401", "flight_date": "2025-06-16", "pnr": "ABC123",
         "first_name": "JOHN", "last_name": "DOE", "airline_code": "6E", "_raw": {}},
        {"flight_number": "6E-1401", "flight_date": "2025-06-16", "pnr": "XYZ789",
         "first_name": "JANE", "last_name": "DOE", "airline_code": "6E", "_raw": {}},
    ]
    count = storage.store_manifest_passengers(aid, "6E", "post_departure", rows)
    assert count == 2


def test_store_manifest_passengers_empty_is_noop():
    storage.mark_processed("e5", "S", "a@b.com", "2024-01-01")
    aid = storage.record_attachment("e5", "empty.xlsx", 100, "c" * 64, "/d/empty.xlsx")
    count = storage.store_manifest_passengers(aid, "TG", "pre_departure", [])
    assert count == 0


def test_store_manifest_passengers_replaces_same_pnr_date_name_with_newer_manifest():
    storage.mark_processed("old-email", "Old Manifest", "a@b.com", "2026-06-24")
    old_aid = storage.record_attachment("old-email", "old.xlsx", 100, "1" * 64, "/d/old.xlsx")
    storage.store_manifest_passengers(
        old_aid,
        "6E",
        "pre_departure",
        [
            {
                "flight_number": "6E101",
                "flight_date": "2026-06-24",
                "pnr": "ABC123",
                "first_name": "John",
                "last_name": "Doe",
                "passport_number": "OLDPASS",
                "seat_number": "1A",
                "_raw": {"source": "old"},
            }
        ],
    )

    storage.mark_processed("new-email", "New Manifest", "a@b.com", "2026-06-24")
    new_aid = storage.record_attachment("new-email", "new.xlsx", 100, "2" * 64, "/d/new.xlsx")
    storage.store_manifest_passengers(
        new_aid,
        "6E",
        "post_departure",
        [
            {
                "flight_number": "6E101",
                "flight_date": "2026-06-24",
                "pnr": "abc123",
                "first_name": " John ",
                "last_name": "DOE",
                "passport_number": "NEWPASS",
                "seat_number": "2B",
                "_raw": {"source": "new"},
            }
        ],
    )

    rows = storage.list_manifest_passengers(query="ABC123")
    assert len(rows) == 1
    assert rows[0]["attachment_id"] == new_aid
    assert rows[0]["manifest_type"] == "post_departure"
    assert rows[0]["passport_number"] == "NEWPASS"
    assert rows[0]["seat_number"] == "2B"


def test_store_manifest_passengers_keeps_same_pnr_name_on_different_dates():
    storage.mark_processed("date-email", "Manifest", "a@b.com", "2026-06-24")
    aid = storage.record_attachment("date-email", "date.xlsx", 100, "3" * 64, "/d/date.xlsx")
    storage.store_manifest_passengers(
        aid,
        "TG",
        "post_departure",
        [
            {"flight_number": "TG1", "flight_date": "2026-06-23", "pnr": "D1", "full_name": "Jane Doe", "_raw": {}},
            {"flight_number": "TG2", "flight_date": "2026-06-24", "pnr": "D1", "full_name": "Jane Doe", "_raw": {}},
        ],
    )

    rows = storage.list_manifest_passengers(query="D1")
    assert len(rows) == 2


def test_heartbeat_inserts():
    # Just verify it doesn't raise
    storage.heartbeat()
    storage.heartbeat()


def test_blacklist_entry_requires_matching_identifier():
    try:
        storage.upsert_blacklist_entry(notes="no useful identifiers")
    except ValueError as exc:
        assert "At least one" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_blacklist_crud_roundtrip():
    created = storage.upsert_blacklist_entry(
        passport="P1234567",
        mobile_no="+91 98765 43210",
        email_id="watch@example.gov",
        name="JOHN DOE",
        notes="client supplied",
    )
    assert created["id"]
    assert created["passport"] == "P1234567"

    updated = storage.upsert_blacklist_entry(
        entry_id=created["id"],
        passport="P7654321",
        mobile_no="9876543210",
        email_id="watch@example.gov",
        name="JOHN DOE",
        notes="updated",
    )
    assert updated["passport"] == "P7654321"
    assert updated["notes"] == "updated"

    rows = storage.list_blacklist_entries()
    assert len(rows) == 1
    assert storage.delete_blacklist_entry(created["id"]) is True
    assert storage.list_blacklist_entries() == []


def test_active_blacklist_alerts_match_passport_phone_email_and_name():
    storage.mark_processed("alert-email", "Manifest", "ops@test.com", "2026-06-24")
    aid = storage.record_attachment("alert-email", "TG.xlsx", 256, "d" * 64, "/d/TG.xlsx")
    storage.store_manifest_passengers(
        aid,
        "TG",
        "post_departure",
        [
            {
                "flight_number": "TG317",
                "flight_date": "2026-06-24",
                "origin": "BKK",
                "destination": "BOM",
                "pnr": "PNR1",
                "full_name": "Jane Public",
                "passport_number": "AA12345",
                "phone": "+91 98765 43210",
                "email": "jane@example.gov",
                "_raw": {},
            }
        ],
    )
    storage.upsert_blacklist_entry(
        passport="aa12345",
        mobile_no="9876543210",
        email_id="JANE@example.gov",
        name="jane public",
    )

    alerts = storage.active_blacklist_alerts()
    assert len(alerts) == 1
    assert alerts[0]["day"] == "2026-06-24"
    assert set(alerts[0]["matched_fields"]) == {"passport", "mobile_no", "email_id", "name"}


def test_passenger_history_by_passport():
    storage.mark_processed("history-email", "Manifest", "ops@test.com", "2026-06-24")
    aid = storage.record_attachment("history-email", "6E.xlsx", 256, "e" * 64, "/d/6E.xlsx")
    storage.store_manifest_passengers(
        aid,
        "6E",
        "post_departure",
        [
            {"flight_number": "6E101", "flight_date": "2026-06-22", "full_name": "Alex One", "passport_number": "HIST1", "_raw": {}},
            {"flight_number": "6E102", "flight_date": "2026-06-24", "full_name": "Alex One", "passport_number": "hist1", "_raw": {}},
            {"flight_number": "6E103", "flight_date": "2026-06-24", "full_name": "Other", "passport_number": "OTHER", "_raw": {}},
        ],
    )

    rows = storage.passenger_history_by_passport("HIST1")
    assert [row["flight_number"] for row in rows] == ["6E102", "6E101"]
