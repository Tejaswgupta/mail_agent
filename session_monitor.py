"""Detect Zoho session expiry / login pages in a Playwright page."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

import notifier

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Patterns that indicate the session has expired or the user is on the login page
_SESSION_EXPIRED_PATTERNS = [
    re.compile(r"accounts\.zoho\.(com|in|eu)/signin", re.IGNORECASE),
    re.compile(r"accounts\.zoho\.(com|in|eu)/oauth", re.IGNORECASE),
    re.compile(r"session.?expired", re.IGNORECASE),
    re.compile(r"sign.?in", re.IGNORECASE),
    re.compile(r"login", re.IGNORECASE),
    re.compile(r"otp", re.IGNORECASE),
    re.compile(r"two.?factor", re.IGNORECASE),
]


def check(page: "Page") -> bool:
    """Return True if the page looks like a login / session-expired page."""
    url = page.url or ""
    title = ""
    try:
        title = page.title() or ""
    except Exception:
        pass

    text_to_check = url + " " + title

    for pattern in _SESSION_EXPIRED_PATTERNS:
        if pattern.search(text_to_check):
            logger.warning(f"Session expiry detected — URL: {url}, title: {title}")
            return True
    return False


def handle_expiry(page: "Page", screenshot_dir: str) -> None:
    """Take screenshot, log, and notify on session expiry."""
    from pathlib import Path
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot_path = str(Path(screenshot_dir) / f"session_expired_{ts}.png")
    try:
        page.screenshot(path=shot_path)
        logger.info(f"Session expiry screenshot saved: {shot_path}")
    except Exception as exc:
        logger.warning(f"Could not capture screenshot: {exc}")
        shot_path = ""

    msg = "⚠️ Zoho Mail session expired — manual login required."
    notifier.send(msg)
    if shot_path:
        try:
            notifier.send_photo(msg, shot_path)
        except Exception:
            pass
