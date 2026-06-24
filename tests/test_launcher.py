"""Tests for launcher browser startup behavior."""
from __future__ import annotations

from unittest.mock import MagicMock

import launcher
from config import settings


class _FakeChromium:
    def __init__(self):
        self.launch_kwargs = None

    def launch_persistent_context(self, **kwargs):
        self.launch_kwargs = kwargs
        return MagicMock()


class _FakePlaywright:
    def __init__(self):
        self.chromium = _FakeChromium()


def test_launch_context_uses_bundled_chromium_by_default(tmp_dirs, monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_CHANNEL", "chromium")
    pw = _FakePlaywright()

    launcher._launch_context(pw)

    assert "channel" not in pw.chromium.launch_kwargs
    assert pw.chromium.launch_kwargs["user_data_dir"] == str(settings.BROWSER_PROFILE_DIR)
    assert pw.chromium.launch_kwargs["downloads_path"] == str(settings.DOWNLOADS_DIR / ".temp")
    assert "--no-first-run" in pw.chromium.launch_kwargs["args"]
    assert "--no-default-browser-check" in pw.chromium.launch_kwargs["args"]


def test_launch_context_can_opt_into_system_chrome(tmp_dirs, monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_CHANNEL", "chrome")
    pw = _FakePlaywright()

    launcher._launch_context(pw)

    assert pw.chromium.launch_kwargs["channel"] == "chrome"


def test_get_or_create_page_closes_restored_tabs():
    restored_page = MagicMock()
    controlled_page = MagicMock()
    context = MagicMock()
    context.pages = [restored_page]

    def new_page():
        context.pages.append(controlled_page)
        return controlled_page

    context.new_page.side_effect = new_page

    assert launcher._get_or_create_page(context) is controlled_page
    restored_page.close.assert_called_once_with()
    controlled_page.close.assert_not_called()
