"""Tests for attachment_processor.py."""
from pathlib import Path
from unittest.mock import MagicMock, patch
import attachment_processor
import storage


def _make_download(tmp_path: Path, filename: str = "invoice.pdf", content: bytes = b"PDF content") -> MagicMock:
    dl = MagicMock()
    dl.suggested_filename = filename

    def save_as(dest: str):
        Path(dest).write_bytes(content)

    dl.save_as.side_effect = save_as
    return dl


def test_process_download_returns_metadata(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", tmp_path / "downloads")
    (tmp_path / "downloads").mkdir(parents=True, exist_ok=True)

    # Pre-insert the email so the FK constraint is satisfied
    storage.mark_processed("email-001", "Subject", "a@b.com", "2024-01-01")

    dl = _make_download(tmp_path, "test.pdf", b"binary pdf data")
    with patch("attachment_processor._parse_and_store"):
        result = attachment_processor.process_download(dl, "email-001")

    assert result is not None
    assert result["file_name"] == "test.pdf"
    assert result["file_size"] == len(b"binary pdf data")
    assert len(result["sha256"]) == 64
    assert "local_path" in result


def test_process_download_xlsx_triggers_parser(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", tmp_path / "downloads")
    (tmp_path / "downloads").mkdir(parents=True, exist_ok=True)

    storage.mark_processed("email-002", "S", "a@b.com", "2024-01-01")
    dl = _make_download(tmp_path, "data.xlsx", b"fake xlsx bytes")

    with patch("attachment_processor.xlsx_parser.parse", return_value={"Sheet1": [{"A": 1}]}) as mock_parse:
        with patch("attachment_processor.storage.store_xlsx_rows", return_value=1) as mock_store:
            attachment_processor.process_download(dl, "email-002")

    mock_parse.assert_called_once()
    mock_store.assert_called_once()


def test_process_download_pdf_triggers_parser(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", tmp_path / "downloads")
    (tmp_path / "downloads").mkdir(parents=True, exist_ok=True)

    storage.mark_processed("email-003", "S", "a@b.com", "2024-01-01")
    dl = _make_download(tmp_path, "report.pdf", b"fake pdf bytes")

    table = {"page_number": 1, "table_index": 0, "headers": ["H"], "rows": [["v"]]}
    with patch("attachment_processor.pdf_parser.parse", return_value=[table]) as mock_parse:
        with patch("attachment_processor.storage.store_pdf_tables") as mock_store:
            attachment_processor.process_download(dl, "email-003")

    mock_parse.assert_called_once()
    mock_store.assert_called_once()


def test_process_download_handles_save_failure(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", tmp_path / "downloads")
    (tmp_path / "downloads").mkdir(parents=True, exist_ok=True)

    dl = MagicMock()
    dl.suggested_filename = "bad.pdf"
    dl.save_as.side_effect = Exception("disk full")

    result = attachment_processor.process_download(dl, "email-fail")
    assert result is None


def test_sha256_correctness(tmp_path):
    import hashlib
    content = b"hello world attachment"
    f = tmp_path / "file.bin"
    f.write_bytes(content)
    result = attachment_processor._sha256(f)
    assert result == hashlib.sha256(content).hexdigest()


def test_local_dir_creates_date_path(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", tmp_path)
    d = attachment_processor._local_dir()
    assert d.exists()


def test_cleanup_downloads_removes_old(tmp_path, monkeypatch):
    from config import settings
    from datetime import date, timedelta
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", tmp_path)

    old = date.today() - timedelta(days=10)
    old_dir = tmp_path / str(old.year) / f"{old.month:02d}" / f"{old.day:02d}"
    old_dir.mkdir(parents=True)
    (old_dir / "file.pdf").write_bytes(b"old")

    attachment_processor.cleanup_downloads(older_than_days=7)
    assert not old_dir.exists()


def test_cleanup_downloads_keeps_recent(tmp_path, monkeypatch):
    from config import settings
    from datetime import date
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", tmp_path)

    today = date.today()
    recent = tmp_path / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}"
    recent.mkdir(parents=True)
    (recent / "file.pdf").write_bytes(b"new")

    attachment_processor.cleanup_downloads(older_than_days=7)
    assert recent.exists()
