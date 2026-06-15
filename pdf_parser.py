"""Extract tables from PDF pages using pdfplumber.

Each page is scanned for tables.  A table is only kept if it has at least one
non-empty row.  The first row of each table is treated as the header row.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore[assignment]


def _clean(value: Any) -> str:
    """Normalise a cell value to a plain string."""
    if value is None:
        return ""
    return str(value).strip()


def parse(path: Path) -> list[dict[str, Any]]:
    """Return a list of table records extracted from the PDF.

    Each record::

        {
            "page_number": int,       # 1-based
            "table_index": int,       # 0-based within the page
            "headers": list[str],
            "rows": list[list[str]],  # data rows (headers excluded)
        }

    Raises ``RuntimeError`` if pdfplumber is not installed.
    Raises ``ValueError`` if the file cannot be opened.
    """
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is not installed — run: pip install pdfplumber")

    try:
        pdf = pdfplumber.open(str(path))
    except Exception as exc:
        raise ValueError(f"Cannot open PDF {path.name}: {exc}") from exc

    results: list[dict[str, Any]] = []

    with pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if not tables:
                continue

            for tbl_idx, table in enumerate(tables):
                # Filter out completely empty rows
                non_empty = [r for r in table if any(_clean(c) for c in r)]
                if not non_empty:
                    continue

                raw_headers = non_empty[0]
                headers = _dedup_headers([_clean(h) for h in raw_headers])
                data_rows = [
                    [_clean(c) for c in row]
                    for row in non_empty[1:]
                ]

                results.append({
                    "page_number": page_num,
                    "table_index": tbl_idx,
                    "headers": headers,
                    "rows": data_rows,
                })
                logger.info(
                    f"Extracted table p{page_num}[{tbl_idx}]: "
                    f"{len(headers)} col(s), {len(data_rows)} row(s)"
                )

    logger.info(f"PDF '{path.name}': {len(results)} table(s) found")
    return results


def _dedup_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for h in headers:
        key = h or "column"
        if key in seen:
            seen[key] += 1
            out.append(f"{key}_{seen[key]}")
        else:
            seen[key] = 0
            out.append(key)
    return out
