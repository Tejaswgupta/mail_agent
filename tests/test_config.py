"""Tests for config.py."""
from pathlib import Path


def test_settings_loads():
    from config import settings
    assert isinstance(settings.DB_PATH, Path)


def test_directories_created():
    from config import settings
    for d in (settings.DOWNLOADS_DIR, settings.LOGS_DIR, settings.SCREENSHOTS_DIR, settings.BROWSER_PROFILE_DIR):
        assert isinstance(d, Path)


def test_poll_interval_default():
    from config import settings
    assert settings.POLL_INTERVAL_SECONDS == 60


def test_zoho_url():
    from config import settings
    assert settings.ZOHO_MAIL_URL.startswith("https://")
    assert "mail_app" in settings.ZOHO_MAIL_URL.lower()
