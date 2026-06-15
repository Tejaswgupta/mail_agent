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


def test_store_xlsx_rows_count():
    storage.mark_processed("e4", "S", "a@b.com", "2024-01-01")
    aid = storage.record_attachment("e4", "data.xlsx", 512, "b" * 64, "/d/data.xlsx")
    count = storage.store_xlsx_rows(aid, "Sheet1", [
        {"Invoice": "001", "Amount": 100},
        {"Invoice": "002", "Amount": 200},
    ])
    assert count == 2


def test_store_xlsx_rows_empty_is_noop():
    storage.mark_processed("e5", "S", "a@b.com", "2024-01-01")
    aid = storage.record_attachment("e5", "empty.xlsx", 100, "c" * 64, "/d/empty.xlsx")
    count = storage.store_xlsx_rows(aid, "Sheet1", [])
    assert count == 0


def test_store_pdf_tables():
    storage.mark_processed("e6", "S", "a@b.com", "2024-01-01")
    aid = storage.record_attachment("e6", "report.pdf", 4096, "d" * 64, "/d/report.pdf")
    storage.store_pdf_tables(
        attachment_id=aid,
        page_number=1,
        table_index=0,
        headers=["Date", "Description", "Amount"],
        rows=[["2024-01-01", "Service fee", "500"]],
    )  # should not raise


def test_heartbeat_inserts():
    # Just verify it doesn't raise
    storage.heartbeat()
    storage.heartbeat()
