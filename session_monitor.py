"""Detect Zoho session expiry / login pages in a Playwright page."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

import notifier

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Positive patterns — logged in if URL or title matches.
_LOGGED_IN_URL_PATTERN = re.compile(r"workplace\.mgovcloud\.in.*#mail_app", re.IGNORECASE)
_LOGGED_IN_TITLE_PATTERN = re.compile(r"inbox|zoho mail", re.IGNORECASE)


def check(page: "Page") -> bool:
    """Return True if the session has expired (i.e. NOT on the mail app)."""
    # Avoid wait_for_load_state("networkidle") — Zoho keeps persistent WS connections
    # open so networkidle never fires, burning 10 s on every call and interrupting
    # the SPA's own initialization on slow Windows machines.
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5_000)
    except Exception:
        pass  # check wherever we are

    url = page.url or ""
    title = ""
    try:
        title = page.title() or ""
    except Exception:
        pass

    if _LOGGED_IN_URL_PATTERN.search(url) or _LOGGED_IN_TITLE_PATTERN.search(title):
        return False  # on mail app — logged in

    logger.warning(f"Session expiry detected — URL: {url}, title: {title}")
    return True


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
