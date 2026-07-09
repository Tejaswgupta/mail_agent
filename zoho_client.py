"""Zoho Mail interaction via Playwright."""

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Generator

from loguru import logger
from playwright.sync_api import Page, Frame, Download, TimeoutError as PWTimeoutError

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


_MAIL_IFRAME_URL = re.compile(r"mail\.mgovcloud\.in", re.IGNORECASE)
_MAIL_READY_SELECTORS = [
    "[role='listbox'][aria-label='Email listing']",
    "[role='listbox'][aria-label*='Email' i]",
    "[role='treeitem'][aria-label*='Inbox' i]",
    "button[aria-label*='Compose' i]",
    "input[aria-label*='Search' i]",
]


def _safe_page_title(page: Page) -> str:
    try:
        return page.title() or ""
    except Exception as exc:
        return f"<title unavailable: {exc}>"


def _safe_ready_state(target) -> str:
    try:
        return target.evaluate("document.readyState")
    except Exception as exc:
        return f"<readyState unavailable: {exc}>"


def _describe_frames(page: Page) -> list[str]:
    frames = []
    for frame in page.frames:
        name = ""
        try:
            name = frame.name
        except Exception:
            pass
        ready_state = _safe_ready_state(frame)
        frames.append(f"name={name!r} ready={ready_state!r} url={frame.url}")
    return frames


def _log_page_snapshot(page: Page, label: str) -> None:
    logger.info(
        f"{label} | url={page.url} | title={_safe_page_title(page)!r} "
        f"| ready={_safe_ready_state(page)!r} | frames={len(page.frames)}"
    )
    for frame_desc in _describe_frames(page):
        logger.debug(f"{label} frame | {frame_desc}")


def _get_mail_frame(page: Page, timeout: int = 15_000) -> Frame | None:
    """Return the Frame for the embedded mail iframe."""
    try:
        page.wait_for_selector("iframe#mailIframe", timeout=timeout)
    except PWTimeoutError:
        pass
    logger.debug(f"Page URL: {page.url} | frames: {[f.url for f in page.frames]}")
    frame = page.frame(url=_MAIL_IFRAME_URL)
    if frame is None:
        logger.warning("Mail iframe (mail.mgovcloud.in) not found — will use page directly")
    else:
        logger.debug(f"Mail frame found: {frame.url[:80]}")
    return frame


def _mail_ui_ready(frame: Frame) -> bool:
    try:
        frame.wait_for_load_state("domcontentloaded", timeout=2_000)
    except Exception:
        pass

    for selector in _MAIL_READY_SELECTORS:
        try:
            if frame.query_selector(selector):
                logger.info(f"Mail UI ready selector matched: {selector}")
                return True
        except Exception:
            continue
    logger.debug(
        "Mail UI ready selectors not found "
        f"| frame_url={frame.url} | ready={_safe_ready_state(frame)!r}"
    )
    return False


def _wait_for_mail_ready(page: Page, timeout: int | None = None) -> bool:
    """Wait until the post-login mail iframe has usable inbox UI."""
    timeout = timeout or settings.ZOHO_READY_TIMEOUT_SECONDS * 1000
    deadline = time.monotonic() + (timeout / 1000)
    started_at = time.monotonic()
    next_snapshot_at = started_at
    last_frame_urls: list[str] = []
    logger.info(f"Waiting up to {timeout // 1000}s for Zoho Mail UI readiness")

    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_snapshot_at:
            elapsed = int(now - started_at)
            _log_page_snapshot(page, f"Zoho readiness wait elapsed={elapsed}s")
            next_snapshot_at = now + 10

        frame = _get_mail_frame(page, timeout=2_000)
        last_frame_urls = [f.url for f in page.frames]
        if frame and _mail_ui_ready(frame):
            elapsed = int(time.monotonic() - started_at)
            logger.info(f"Zoho Mail UI ready after {elapsed}s")
            return True
        time.sleep(2)

    logger.warning(
        "Zoho Mail UI did not become ready. "
        f"Page URL: {page.url} | frames: {last_frame_urls}"
    )
    _screenshot(page, "mail_not_ready")
    dump_mail_frame_html(page, "mail_not_ready")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Login / session management
# ─────────────────────────────────────────────────────────────────────────────

def ensure_logged_in(page: Page) -> bool:
    """Navigate to Zoho Mail, wait for user to log in if needed. Returns True on success."""
    logger.info("Navigating to Zoho Mail…")
    _log_page_snapshot(page, "Before Zoho navigation")
    page.goto(settings.ZOHO_MAIL_URL, wait_until="domcontentloaded", timeout=60_000)
    _log_page_snapshot(page, "After Zoho navigation")

    # Wait for DOM to settle; avoid "networkidle" since Zoho keeps WS connections
    # alive indefinitely, so networkidle never fires and stalls the SPA boot.
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:
        pass  # timeout is fine — just check wherever we ended up
    _log_page_snapshot(page, "After Zoho DOM settle")

    if not session_monitor.check(page):
        logger.info("Already logged in — waiting for mail UI")
        return _wait_for_mail_ready(page)

    logger.info("Login required — waiting for manual login…")
    import notifier
    notifier.send("🔐 Zoho Mail login required. Please open the browser and sign in.")

    input("Log in to Zoho Mail in the browser, then press Enter here to continue…")
    _log_page_snapshot(page, "After manual login confirmation")

    if not session_monitor.check(page):
        logger.info("Login detected — waiting for mail UI")
        return _wait_for_mail_ready(page)

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
    frame = _get_mail_frame(page)
    if frame is None:
        return emails
    try:
        frame.wait_for_selector("[role='listbox'][aria-label='Email listing']", timeout=15_000)
    except PWTimeoutError:
        logger.warning("Email listing listbox not found within timeout")
        return emails

    rows = frame.query_selector_all("[role='listbox'][aria-label='Email listing'] [role='option']")
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
                "i.msi-attachicon, button[aria-label*='attachment' i]"
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
    frame = _get_mail_frame(page)
    try:
        if frame:
            inbox = frame.query_selector("[role='treeitem'][aria-label*='Inbox' i]")
            if inbox:
                inbox.click()
                time.sleep(2)
            else:
                page.goto(settings.ZOHO_MAIL_URL, wait_until="domcontentloaded", timeout=30_000)
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
    """Click on an email row and wait for the reading pane to navigate to it."""
    frame = _get_mail_frame(page)
    if frame is None:
        return False
    try:
        pre_url = frame.url
        if row_handle is not None:
            row_handle.click()
        else:
            rows = frame.query_selector_all("[role='listbox'][aria-label='Email listing'] [role='option']")
            import hashlib
            matched = next(
                (r for r in rows if hashlib.md5((r.get_attribute("aria-label") or "").encode()).hexdigest() == email_id),
                None,
            )
            if not matched:
                logger.warning(f"Could not find email row for id {email_id}")
                return False
            matched.click()

        # Wait for the frame URL to change to an individual email view (/p/<id>)
        try:
            frame.wait_for_function(
                f"() => window.location.href !== {repr(pre_url)} && window.location.href.includes('/p/')",
                timeout=10_000,
            )
        except PWTimeoutError:
            # May already be on a /p/ URL (e.g. first email opened); that's fine
            pass

        return True
    except Exception as exc:
        logger.warning(f"Could not open email {email_id}: {exc}")
    return False


def get_email_body(page: Page) -> str:
    """Return the plain text of the currently-open email's reading pane."""
    frame = _get_mail_frame(page)
    if frame is None:
        return ""

    # Wait for reading pane to be ready (same gate used by iter_attachments)
    try:
        frame.wait_for_selector(".zmMailActions", timeout=15_000)
    except PWTimeoutError:
        logger.debug("get_email_body: reading pane did not load")
        return ""

    # Try candidates in order — the first one that exists wins
    selectors = [
        ".zmMailReadMessagePane",
        ".zmail-readpane-body",
        ".zmMailViewPane",
        ".mail-view-pane",
    ]

    # Some Zoho deployments render the body inside a nested content iframe
    for iframe_sel in ("iframe#mailcontent", "iframe[id*='mailcontent']"):
        try:
            el = frame.query_selector(iframe_sel)
            if el:
                child_frame = el.content_frame()
                if child_frame:
                    try:
                        text = child_frame.locator("body").inner_text(timeout=5_000)
                        if text.strip():
                            return text.strip()
                    except Exception:
                        pass
        except Exception:
            pass

    for sel in selectors:
        try:
            el = frame.query_selector(sel)
            if el:
                text = el.inner_text()
                if text.strip():
                    return text.strip()
        except Exception:
            continue

    logger.debug("get_email_body: no selector matched reading pane content")
    return ""


def dump_mail_frame_html(page: Page, label: str = "frame_dump") -> None:
    """Save the current mail iframe HTML to screenshots dir for selector debugging."""
    frame = _get_mail_frame(page)
    if frame is None:
        logger.warning("dump_mail_frame_html: mail frame not found")
        return
    try:
        html = frame.content()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = settings.SCREENSHOTS_DIR / f"{label}_{ts}.html"
        path.write_text(html, encoding="utf-8")
        logger.info(f"Mail frame HTML dumped to: {path}")
    except Exception as exc:
        logger.warning(f"dump_mail_frame_html failed: {exc}")


def iter_attachments(page: Page, email_id: str) -> Generator[Download, None, None]:
    """Yield Playwright Download objects for every attachment in the currently open email."""
    frame = _get_mail_frame(page)
    if frame is None:
        return

    # Wait for the reading pane to finish loading (zmMailActions appears once email body is ready).
    # Then check if an attachment section exists at all before waiting longer.
    try:
        frame.wait_for_selector(".zmMailActions", timeout=15_000)
    except PWTimeoutError:
        logger.debug(f"Reading pane did not load for email {email_id} — skipping attachments")
        return

    # Download buttons are inside zmattachment__actions--onhover__860ix0 — CSS-hidden until hover.
    # Wait for the attachment items to be attached to DOM (not visible), then hover each to
    # reveal the button before clicking.
    item_sel = "[data-attachment-item='true']"
    try:
        frame.wait_for_selector(item_sel, state="attached", timeout=5_000)
    except PWTimeoutError:
        logger.debug(f"No attachments found in email {email_id}")
        return

    items = frame.query_selector_all(item_sel)
    logger.info(f"Found {len(items)} attachment(s) in email {email_id}")

    for item in items:
        try:
            item.hover()  # trigger CSS :hover to reveal the action buttons
            btn = item.query_selector("button[data-testid='Attachment_Download_mail']")
            if btn is None:
                logger.warning(f"Download button not found on attachment item in {email_id}")
                continue
            with page.expect_download(timeout=60_000) as dl_info:
                btn.click(force=True)
            yield dl_info.value
        except PWTimeoutError:
            logger.warning(f"Download timeout for an attachment in email {email_id}")
        except Exception as exc:
            logger.error(f"Attachment download error in email {email_id}: {exc}")
