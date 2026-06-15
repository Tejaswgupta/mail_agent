"""Download attachments, parse xlsx/pdf, store everything in SQLite."""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from config import settings
import storage
import xlsx_parser
import pdf_parser

if TYPE_CHECKING:
    from playwright.sync_api import Download


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _local_dir() -> Path:
    today = date.today()
    d = settings.DOWNLOADS_DIR / "Votum" / f"{today.year}" / f"{today.month:02d}" / f"{today.day:02d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_and_store(attachment_id: str, path: Path) -> None:
    """Dispatch to the right parser based on file extension."""
    suffix = path.suffix.lower()

    if suffix in (".xlsx", ".xls"):
        try:
            sheets = xlsx_parser.parse(path)
            for sheet_name, rows in sheets.items():
                storage.store_xlsx_rows(attachment_id, sheet_name, rows)
        except Exception as exc:
            logger.error(f"xlsx parse failed for {path.name}: {exc}")

    elif suffix == ".pdf":
        try:
            tables = pdf_parser.parse(path)
            for tbl in tables:
                storage.store_pdf_tables(
                    attachment_id=attachment_id,
                    page_number=tbl["page_number"],
                    table_index=tbl["table_index"],
                    headers=tbl["headers"],
                    rows=tbl["rows"],
                )
        except Exception as exc:
            logger.error(f"pdf parse failed for {path.name}: {exc}")

    else:
        logger.debug(f"No parser for extension '{suffix}' — skipping parse for {path.name}")


def process_download(download: "Download", email_id: str) -> dict | None:
    """Save a Playwright Download, hash it, parse it, store metadata. Returns meta dict or None."""
    local_dir = _local_dir()
    dest = local_dir / download.suggested_filename

    # Avoid overwriting if filename collides
    counter = 1
    while dest.exists():
        stem = Path(download.suggested_filename).stem
        suffix = Path(download.suggested_filename).suffix
        dest = local_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    try:
        try:
            download.save_as(str(dest))
        except Exception as exc:
            logger.error(f"Failed to save download {download.suggested_filename}: {exc}")
            return None

        sha = _sha256(dest)
        size = dest.stat().st_size

        try:
            attachment_id = storage.record_attachment(
                email_id=email_id,
                file_name=dest.name,
                file_size=size,
                sha256=sha,
                local_path=str(dest),
            )
        except Exception as exc:
            logger.error(f"DB record failed for {dest.name}: {exc}")
            return None

        _parse_and_store(attachment_id, dest)

        return {
            "file_name": dest.name,
            "file_size": size,
            "sha256": sha,
            "local_path": str(dest),
        }
    finally:
        try:
            download.delete()
        except Exception as exc:
            logger.warning(f"Could not delete temporary download file: {exc}")


# ── Cleanup ───────────────────────────────────────────────────────────────────

def _rmtree_windows_safe(path: Path) -> None:
    def _on_error(func, fpath, exc_info):
        try:
            os.chmod(fpath, stat.S_IWRITE)
            func(fpath)
        except Exception as e:
            logger.warning(f"Could not remove {fpath}: {e}")

    shutil.rmtree(path, onerror=_on_error)


def cleanup_downloads(older_than_days: int = 7) -> None:
    """Remove local download dirs older than *older_than_days*."""
    today = date.today()
    votum_dir = settings.DOWNLOADS_DIR / "Votum"
    if not votum_dir.exists():
        return
    for year_dir in votum_dir.iterdir():
        if not year_dir.is_dir():
            continue
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir():
                continue
            for day_dir in month_dir.iterdir():
                if not day_dir.is_dir():
                    continue
                try:
                    d = date(int(year_dir.name), int(month_dir.name), int(day_dir.name))
                    if (today - d).days > older_than_days:
                        _rmtree_windows_safe(day_dir)
                        logger.info(f"Cleaned up {day_dir}")
                except (ValueError, OSError) as exc:
                    logger.warning(f"Could not clean {day_dir}: {exc}")
