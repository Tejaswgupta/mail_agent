"""Tests for notifier.py."""
from unittest.mock import MagicMock, patch
import notifier


def test_send_returns_false_without_credentials(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    result = notifier.send("hello")
    assert result is False


def test_send_returns_true_with_credentials(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "bottoken")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "12345")
    with patch("notifier.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)
        result = notifier.send("test message")
    assert result is True


def test_send_handles_network_error(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "bottoken")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "12345")
    with patch("notifier.requests.post", side_effect=Exception("network error")):
        result = notifier.send("test message")
    assert result is False


def test_send_photo_no_credentials(monkeypatch, tmp_path):
    from config import settings
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    fake_photo = tmp_path / "photo.png"
    fake_photo.write_bytes(b"fake")
    result = notifier.send_photo("caption", str(fake_photo))
    assert result is False
