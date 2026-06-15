"""Tests for watcher.py."""
from unittest.mock import MagicMock, patch, call
import watcher


def _make_page(url: str = "https://mail.zoho.com/zm/#mail/inbox") -> MagicMock:
    page = MagicMock()
    page.url = url
    page.title.return_value = "Zoho Mail"
    return page


def test_run_once_skips_already_processed(monkeypatch):
    page = _make_page()
    emails = [{"email_id": "e1", "subject": "Test", "sender": "a@b.com", "received_at": "2024-01-01"}]

    with patch("watcher.session_monitor.check", return_value=False):
        with patch("watcher.zoho_client.get_inbox_emails", return_value=emails):
            with patch("watcher.storage.is_processed", return_value=True):
                with patch("watcher.zoho_client.open_email") as mock_open:
                    count = watcher.run_once(page)

    assert count == 0
    mock_open.assert_not_called()


def test_run_once_processes_new_email(monkeypatch):
    page = _make_page()
    emails = [{"email_id": "e2", "subject": "Hello", "sender": "x@y.com", "received_at": "2024-01-02"}]
    mock_download = MagicMock()

    with patch("watcher.session_monitor.check", return_value=False):
        with patch("watcher.zoho_client.get_inbox_emails", return_value=emails):
            with patch("watcher.storage.is_processed", return_value=False):
                with patch("watcher.zoho_client.open_email", return_value=True):
                    with patch("watcher.zoho_client.iter_attachments", return_value=iter([mock_download])):
                        with patch("watcher.attachment_processor.process_download", return_value={"file_name": "f.pdf", "file_size": 100, "sha256": "abc", "storage_path": "x"}):
                            with patch("watcher.storage.mark_processed") as mock_mark:
                                count = watcher.run_once(page)

    assert count == 1
    mock_mark.assert_called_once_with(
        email_id="e2", subject="Hello", sender="x@y.com", received_at="2024-01-02"
    )


def test_run_once_pauses_on_session_expiry():
    page = _make_page("https://accounts.zoho.com/signin")

    with patch("watcher.session_monitor.check", return_value=True):
        with patch("watcher.session_monitor.handle_expiry") as mock_handle:
            with patch("watcher.zoho_client.get_inbox_emails") as mock_get:
                count = watcher.run_once(page)

    assert count == 0
    mock_handle.assert_called_once()
    mock_get.assert_not_called()


def test_run_once_handles_db_check_failure():
    page = _make_page()
    emails = [{"email_id": "e3", "subject": "S", "sender": "s@s.com", "received_at": "2024-01-03"}]

    with patch("watcher.session_monitor.check", return_value=False):
        with patch("watcher.zoho_client.get_inbox_emails", return_value=emails):
            with patch("watcher.storage.is_processed", side_effect=Exception("db down")):
                count = watcher.run_once(page)

    assert count == 0


def test_run_once_skips_email_with_no_id():
    page = _make_page()
    emails = [{"email_id": "", "subject": "no id", "sender": "x@y.com", "received_at": "now"}]

    with patch("watcher.session_monitor.check", return_value=False):
        with patch("watcher.zoho_client.get_inbox_emails", return_value=emails):
            with patch("watcher.storage.is_processed") as mock_is:
                count = watcher.run_once(page)

    assert count == 0
    mock_is.assert_not_called()
