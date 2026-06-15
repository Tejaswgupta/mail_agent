"""Tests for session_monitor.py."""
from unittest.mock import MagicMock, patch
import session_monitor


def _make_page(url: str, title: str = "") -> MagicMock:
    page = MagicMock()
    page.url = url
    page.title.return_value = title
    return page


def test_login_url_detected():
    page = _make_page("https://accounts.zoho.com/signin?servicename=zohomailnew")
    assert session_monitor.check(page) is True


def test_oauth_url_detected():
    page = _make_page("https://accounts.zoho.com/oauth/v2/auth?...")
    assert session_monitor.check(page) is True


def test_normal_inbox_not_detected():
    page = _make_page("https://mail.zoho.com/zm/#mail/inbox", "Zoho Mail")
    # "mail" contains "mail" but we only match specific patterns
    # The check should return False for normal inbox
    result = session_monitor.check(page)
    # "login" is not in the inbox URL/title so should be False
    assert result is False


def test_session_expired_in_title():
    page = _make_page("https://mail.zoho.com/", "Session Expired")
    assert session_monitor.check(page) is True


def test_otp_page_detected():
    page = _make_page("https://accounts.zoho.com/otp")
    assert session_monitor.check(page) is True


def test_handle_expiry_takes_screenshot(tmp_path, monkeypatch):
    page = _make_page("https://accounts.zoho.com/signin")
    page.screenshot = MagicMock()
    with patch("session_monitor.notifier.send", return_value=True):
        with patch("session_monitor.notifier.send_photo", return_value=True):
            session_monitor.handle_expiry(page, str(tmp_path))
    page.screenshot.assert_called_once()
    shot_path = page.screenshot.call_args[1]["path"]
    assert "session_expired" in shot_path


def test_handle_expiry_screenshot_failure_does_not_crash(tmp_path):
    page = _make_page("https://accounts.zoho.com/signin")
    page.screenshot.side_effect = Exception("screenshot failed")
    with patch("session_monitor.notifier.send", return_value=True):
        with patch("session_monitor.notifier.send_photo", return_value=True):
            session_monitor.handle_expiry(page, str(tmp_path))  # should not raise
