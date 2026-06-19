"""Zoho Mail interaction via Playwright."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Generator

from loguru import logger
from playwright.sync_api import Page, Download, TimeoutError as PWTimeoutError

from config import settings
import session_monitor


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _screenshot(page: Page, name: str) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = settings.SCREENSHOTS_DIR / f"{name}_{ts}.png"
    try:
        page.screenshot(path=str(path))
        logger.debug(f"Screenshot saved: {path}")
    except Exception as exc:
        logger.warning(f"Screenshot failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Login / session management
# ─────────────────────────────────────────────────────────────────────────────

def ensure_logged_in(page: Page) -> bool:
    """Navigate to Zoho Mail, wait for user to log in if needed. Returns True on success."""
    logger.info("Navigating to Zoho Mail…")
    page.goto(settings.ZOHO_MAIL_URL, wait_until="domcontentloaded", timeout=60_000)

    # Wait for network to go idle so any auth redirect has fully landed.
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass  # timeout is fine — just check wherever we ended up

    if not session_monitor.check(page):
        logger.info("Already logged in")
        return True

    logger.info("Login required — waiting for manual login…")
    import notifier
    notifier.send("🔐 Zoho Mail login required. Please open the browser and sign in.")

    input("Log in to Zoho Mail in the browser, then press Enter here to continue…")

    if not session_monitor.check(page):
        logger.info("Login detected — continuing")
        return True

    logger.error("Login check failed after user confirmed")
    _screenshot(page, "login_failed")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Email listing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_aria_label(label: str) -> dict:
    """Extract subject, sender, received_at from an email option's aria-label.

    Zoho format: "Unread email , From <sender>, Subject <subject>, Received time <time>[, N attachments]"
    """
    import re
    sender = ""
    subject = ""
    received_at = datetime.now().isoformat()

    m = re.search(r"From (.+?), Subject", label)
    if m:
        sender = m.group(1).strip()

    m = re.search(r"Subject (.+?), Received time", label)
    if m:
        subject = m.group(1).strip()

    m = re.search(r"Received time (.+?)(?:,|$)", label)
    if m:
        received_at = m.group(1).strip()

    return {"sender": sender, "subject": subject, "received_at": received_at}


def _parse_email_rows(page: Page) -> list[dict]:
    """Parse email rows from the inbox. Returns list of dicts with email metadata."""
    emails: list[dict] = []
    try:
        # Real Zoho UI: email list is a listbox with role=listbox
        page.wait_for_selector("[role='listbox'][aria-label='Email listing']", timeout=15_000)
    except PWTimeoutError:
        logger.warning("Email listing listbox not found within timeout")
        return emails

    rows = page.query_selector_all("[role='listbox'][aria-label='Email listing'] [role='option']")
    for row in rows:
        try:
            label = row.get_attribute("aria-label") or ""
            if not label:
                continue
            # Use aria-label as a stable email ID (hash it to keep it short)
            import hashlib
            email_id = hashlib.md5(label.encode()).hexdigest()
            meta = _parse_aria_label(label)
            has_attachment = row.query_selector(
                "button[title*='attachment' i], button[aria-label*='attachment' i]"
            ) is not None
            emails.append({
                "email_id": email_id,
                "aria_label": label,
                "subject": meta["subject"],
                "sender": meta["sender"],
                "received_at": meta["received_at"],
                "has_attachment": has_attachment,
                "_row_handle": row,  # kept for open_email — not stored in DB
            })
        except Exception as exc:
            logger.debug(f"Row parse error: {exc}")
            continue

    logger.debug(f"Found {len(emails)} email rows")
    return emails


def get_inbox_emails(page: Page) -> list[dict]:
    """Navigate to inbox and return a list of email metadata dicts."""
    try:
        # Real Zoho UI: inbox is a treeitem in the left nav
        inbox = page.query_selector("[role='treeitem'][aria-label*='Inbox' i]")
        if inbox:
            inbox.click()
            time.sleep(2)
        else:
            page.goto(settings.ZOHO_MAIL_URL, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(2)
    except Exception as exc:
        logger.warning(f"Could not navigate to inbox: {exc}")

    return _parse_email_rows(page)


# ─────────────────────────────────────────────────────────────────────────────
# Attachment download
# ─────────────────────────────────────────────────────────────────────────────

def open_email(page: Page, email_id: str, row_handle=None) -> bool:
    """Click on an email row. Prefers the stored handle, falls back to aria-label search."""
    try:
        if row_handle is not None:
            row_handle.click()
        else:
            # Fallback: find by aria-label containing the email_id (not reliable — prefer handle)
            rows = page.query_selector_all("[role='listbox'][aria-label='Email listing'] [role='option']")
            import hashlib
            matched = next(
                (r for r in rows if hashlib.md5((r.get_attribute("aria-label") or "").encode()).hexdigest() == email_id),
                None,
            )
            if not matched:
                logger.warning(f"Could not find email row for id {email_id}")
                return False
            matched.click()
        time.sleep(1)
        return True
    except Exception as exc:
        logger.warning(f"Could not open email {email_id}: {exc}")
    return False


def iter_attachments(page: Page, email_id: str) -> Generator[Download, None, None]:
    """Yield Playwright Download objects for every attachment in the currently open email."""
    # Real Zoho UI: after opening an email, download buttons have title containing 'Download'
    try:
        page.wait_for_selector(
            "button[title*='Download' i], a[title*='Download' i]",
            timeout=5_000,
        )
    except PWTimeoutError:
        logger.debug(f"No attachments found in email {email_id}")
        return

    attachment_links = page.query_selector_all(
        "button[title*='Download' i], a[title*='Download' i]"
    )
    logger.info(f"Found {len(attachment_links)} attachment link(s) in email {email_id}")

    for link in attachment_links:
        try:
            with page.expect_download(timeout=60_000) as dl_info:
                link.click()
            yield dl_info.value
        except PWTimeoutError:
            logger.warning(f"Download timeout for an attachment in email {email_id}")
        except Exception as exc:
            logger.error(f"Attachment download error in email {email_id}: {exc}")
