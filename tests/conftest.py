"""Shared pytest fixtures — isolated SQLite DB per test, stubbed Telegram."""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Add mail_agent root to path so modules resolve without package prefix
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point storage at a fresh in-memory-style SQLite file for every test."""
    db_path = tmp_path / "test.db"
    from config import settings
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    # Re-import storage so it picks up the patched DB_PATH
    import storage
    storage.init_db()
    yield db_path


@pytest.fixture(autouse=True)
def patch_telegram():
    """Stub out requests.post so Telegram calls never hit the network."""
    with patch("notifier.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)
        yield mock_post


@pytest.fixture()
def tmp_dirs(tmp_path, monkeypatch):
    """Redirect all file-system paths to tmp_path for isolation."""
    from config import settings
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", tmp_path / "downloads")
    monkeypatch.setattr(settings, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(settings, "SCREENSHOTS_DIR", tmp_path / "screenshots")
    monkeypatch.setattr(settings, "BROWSER_PROFILE_DIR", tmp_path / "browser_profile")
    for d in ("downloads", "logs", "screenshots", "browser_profile"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path
