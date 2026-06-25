"""Core inbox-watching loop — polls Zoho Mail every POLL_INTERVAL_SECONDS."""

import time
from datetime import datetime

from loguru import logger
from playwright.sync_api import Page

import notifier
import session_monitor
import storage
import zoho_client
import attachment_processor
from config import settings


def _screenshot(page: Page, name: str) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = settings.SCREENSHOTS_DIR / f"{name}_{ts}.png"
    try:
        page.screenshot(path=str(path))
    except Exception:
        pass


def run_once(page: Page) -> int:
    """Single polling pass. Returns number of emails processed."""
    # Session check first
    if session_monitor.check(page):
        session_monitor.handle_expiry(page, str(settings.SCREENSHOTS_DIR))
        return 0

    emails = zoho_client.get_inbox_emails(page)
    processed_count = 0
    consecutive_seen = 0
    EARLY_EXIT_THRESHOLD = 3

    for email in emails:
        email_id = email["email_id"]
        if not email_id:
            continue

        try:
            if storage.is_processed(email_id):
                consecutive_seen += 1
                if consecutive_seen >= EARLY_EXIT_THRESHOLD:
                    logger.debug(f"Last {EARLY_EXIT_THRESHOLD} emails already processed — stopping scan")
                    break
                logger.debug(f"Skipping already-processed email {email_id}")
                continue
        except Exception as exc:
            logger.error(f"DB check failed for {email_id}: {exc}")
            continue

        consecutive_seen = 0  # reset on any new email

        logger.info(f"Processing email: {email_id} | {email['subject']}")

        if not email.get("has_attachment"):
            logger.debug(f"No attachment indicator on email {email_id} — skipping download")
            try:
                storage.mark_processed(
                    email_id=email_id,
                    subject=email["subject"],
                    sender=email["sender"],
                    received_at=email["received_at"],
                )
                processed_count += 1
            except Exception as exc:
                logger.error(f"mark_processed failed for {email_id}: {exc}")
            continue

        if not zoho_client.open_email(page, email_id, row_handle=email.get("_row_handle")):
            logger.warning(f"Could not open email {email_id} — skipping")
            continue

        # Mark processed before downloading so the FK constraint on attachments is satisfied.
        try:
            storage.mark_processed(
                email_id=email_id,
                subject=email["subject"],
                sender=email["sender"],
                received_at=email["received_at"],
            )
            processed_count += 1
        except Exception as exc:
            logger.error(f"mark_processed failed for {email_id}: {exc}")
            continue

        for download in zoho_client.iter_attachments(page, email_id):
            try:
                meta = attachment_processor.process_download(download, email_id)
                if meta:
                    logger.info(f"Attachment processed: {meta['file_name']} ({meta['file_size']} bytes)")
                else:
                    logger.warning(f"process_download returned None for an attachment in {email_id}")
            except Exception as exc:
                logger.error(f"Attachment processing error ({email_id}): {exc}")
                _screenshot(page, f"attach_error_{email_id}")

    return processed_count


def watch(page: Page) -> None:
    """Blocking watch loop. Runs until interrupted."""
    logger.info("Watcher started — poll interval: %ds", settings.POLL_INTERVAL_SECONDS)
    notifier.send("✅ Zoho Mail watcher started")

    while True:
        try:
            storage.heartbeat()
        except Exception as exc:
            logger.warning(f"Heartbeat failed: {exc}")

        try:
            if session_monitor.check(page):
                session_monitor.handle_expiry(page, str(settings.SCREENSHOTS_DIR))
                if not zoho_client.ensure_logged_in(page):
                    logger.error("Re-login failed — stopping watcher")
                    return
                logger.info("Re-login successful — resuming watcher")
                continue

            count = run_once(page)
            if count:
                logger.info(f"Poll complete — processed {count} new email(s)")
            else:
                logger.debug("Poll complete — no new emails")
        except Exception as exc:
            logger.error(f"Poll error: {exc}")
            _screenshot(page, "poll_error")

        time.sleep(settings.POLL_INTERVAL_SECONDS)
