"""One-shot task extraction: iterate new inbox emails, call Votum AI, push to Supabase."""

from pathlib import Path

import requests
from loguru import logger
from playwright.sync_api import Page

import notifier
import storage
import supabase_client
import zoho_client
from config import settings

EARLY_EXIT_THRESHOLD = 3
ATTACHMENT_TEXT_LIMIT = 4_000  # chars per file


def _attachment_text(email_id: str) -> str:
    """Return concatenated plain text from locally-stored attachments for this email."""
    attachments = storage.list_attachments_for_email(email_id)
    parts: list[str] = []
    for att in attachments:
        path = Path(att["local_path"])
        if not path.exists():
            logger.debug(f"Attachment file missing, skipping: {path}")
            continue
        try:
            text = _read_file_as_text(path)
            if text:
                parts.append(f"[Attachment: {att['file_name']}]\n{text}")
        except Exception as exc:
            logger.warning(f"Could not read attachment {path}: {exc}")
    return "\n\n".join(parts)


def _read_file_as_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages_text = [p.extract_text() or "" for p in pdf.pages]
        return _cap("\n".join(pages_text))
    if suffix in {".xlsx", ".xls"}:
        return _cap(_read_spreadsheet(path))
    if suffix == ".csv":
        return _cap(path.read_text(encoding="utf-8", errors="replace"))
    return ""


def _read_spreadsheet(path: Path) -> str:
    suffix = path.suffix.lower()
    rows_text: list[str] = []
    if suffix == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for sheet in wb.worksheets:
            headers: list[str] = []
            for i, row in enumerate(sheet.iter_rows(values_only=True)):
                if i == 0:
                    headers = [str(c) if c is not None else "" for c in row]
                else:
                    pairs = [f"{h}: {v}" for h, v in zip(headers, row) if v is not None]
                    if pairs:
                        rows_text.append(", ".join(pairs))
        wb.close()
    else:
        import xlrd
        wb = xlrd.open_workbook(str(path))
        for sheet in wb.sheets():
            headers: list[str] = []
            for i in range(sheet.nrows):
                row = sheet.row_values(i)
                if i == 0:
                    headers = [str(c) for c in row]
                else:
                    pairs = [f"{h}: {v}" for h, v in zip(headers, row) if v != ""]
                    if pairs:
                        rows_text.append(", ".join(pairs))
    return "\n".join(rows_text)


def _cap(text: str) -> str:
    return text[:ATTACHMENT_TEXT_LIMIT]


def _call_ai_api(text: str) -> dict:
    try:
        headers = {"x-api-key": settings.VOTUM_API_ACCESS_TOKEN} if settings.VOTUM_API_ACCESS_TOKEN else {}
        resp = requests.post(
            settings.VOTUM_AI_API_URL,
            json={"text": text},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning(f"AI API call failed: {exc}")
        return {"requires_action": False, "tasks": None}


def run(page: Page) -> None:
    """Process inbox emails for task extraction. Exits after one full pass."""
    logger.info("Task extraction mode starting")
    notifier.send("🔍 Task extraction starting…")

    if not settings.VOTUM_SUPABASE_URL or not settings.VOTUM_SUPABASE_KEY:
        logger.error("VOTUM_SUPABASE_URL and VOTUM_SUPABASE_KEY must be set in .env")
        notifier.send("❌ Task extraction failed: Supabase credentials not configured")
        return

    if not settings.VOTUM_USER_ID:
        logger.error("VOTUM_USER_ID must be set in .env")
        notifier.send("❌ Task extraction failed: VOTUM_USER_ID not configured")
        return

    if not settings.VOTUM_API_ACCESS_TOKEN:
        logger.error("VOTUM_API_ACCESS_TOKEN must be set in .env")
        notifier.send("❌ Task extraction failed: VOTUM_API_ACCESS_TOKEN not configured")
        return

    emails = zoho_client.get_inbox_emails(page)
    if not emails:
        logger.info("No emails found in inbox")
        notifier.send("📭 Task extraction: inbox empty")
        return

    total_tasks = 0
    processed = 0
    consecutive_seen = 0

    for email in emails:
        email_id = email["email_id"]

        if supabase_client.is_task_extracted(email_id):
            consecutive_seen += 1
            if consecutive_seen >= EARLY_EXIT_THRESHOLD:
                logger.info("Early exit: reached already-extracted emails")
                break
            continue

        consecutive_seen = 0

        logger.info(f"Processing email: {email['subject']!r} from {email['sender']!r}")
        zoho_client.open_email(page, email_id, email["_row_handle"])

        body_text = zoho_client.get_email_body(page)
        attachment_text = _attachment_text(email_id)
        combined = "\n\n".join(filter(None, [body_text, attachment_text])).strip()

        if not combined:
            logger.debug(f"Email {email_id} has no extractable text — skipping")
            processed += 1
            continue

        logger.debug(f"Sending {len(combined)} chars to AI API for {email_id}")
        ai_result = _call_ai_api(combined)
        tasks = ai_result.get("tasks") or []

        if tasks and ai_result.get("requires_action"):
            supabase_client.save_suggested_tasks(tasks, email_id, settings.VOTUM_USER_ID)
            total_tasks += len(tasks)
            notifier.send(
                f"✅ {len(tasks)} task(s) from: {email['subject']}\n"
                + "\n".join(f"• {t['task_title']}" for t in tasks)
            )
        else:
            logger.debug(f"No actionable tasks for email {email_id} (requires_action={ai_result.get('requires_action')})")

        processed += 1

    summary = f"Task extraction done — {processed} email(s) scanned, {total_tasks} task(s) created"
    logger.info(summary)
    notifier.send(f"✔️ {summary}")
