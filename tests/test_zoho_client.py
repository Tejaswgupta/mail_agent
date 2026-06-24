"""Tests for Zoho Mail browser interaction helpers."""
from __future__ import annotations

from unittest.mock import MagicMock

import zoho_client


def test_wait_for_mail_ready_requires_mail_ui(monkeypatch):
    frame = MagicMock()
    frame.query_selector.side_effect = lambda selector: MagicMock() if "Inbox" in selector else None
    page = MagicMock()
    page.frames = [frame]

    monkeypatch.setattr(zoho_client, "_get_mail_frame", lambda page, timeout=15_000: frame)

    assert zoho_client._wait_for_mail_ready(page, timeout=100) is True


def test_mail_ui_ready_returns_false_without_known_selectors():
    frame = MagicMock()
    frame.query_selector.return_value = None

    assert zoho_client._mail_ui_ready(frame) is False
