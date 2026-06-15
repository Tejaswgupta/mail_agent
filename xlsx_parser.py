"""Parse xlsx attachments with a fixed schema into a list of row dicts.

Each sheet is parsed independently.  The first non-empty row is treated as the
header row.  Every subsequent row becomes a dict keyed by those headers.
Empty rows (all cells blank) are skipped.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger
import openpyxl
from openpyxl.utils.exceptions import InvalidFileException


def parse(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Return ``{sheet_name: [row_dict, ...]}`` for every sheet in the workbook.

    Raises ``ValueError`` if the file cannot be opened as a workbook.
    """
    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except (InvalidFileException, Exception) as exc:
        raise ValueError(f"Cannot open xlsx file {path.name}: {exc}") from exc

    result: dict[str, list[dict[str, Any]]] = {}

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            logger.debug(f"Sheet '{sheet_name}' is empty — skipping")
            continue

        # Find the first row that has at least one non-None cell → headers
        header_idx = next(
            (i for i, r in enumerate(rows) if any(c is not None for c in r)),
            None,
        )
        if header_idx is None:
            logger.debug(f"Sheet '{sheet_name}' has no non-empty rows — skipping")
            continue

        raw_headers = rows[header_idx]
        # Deduplicate blank/None header names so dict keys are unique
        headers: list[str] = []
        seen: dict[str, int] = {}
        for h in raw_headers:
            key = str(h).strip() if h is not None else "column"
            if key in seen:
                seen[key] += 1
                key = f"{key}_{seen[key]}"
            else:
                seen[key] = 0
            headers.append(key)

        data_rows: list[dict[str, Any]] = []
        for row in rows[header_idx + 1 :]:
            if all(c is None for c in row):
                continue  # skip blank rows
            data_rows.append(dict(zip(headers, row)))

        result[sheet_name] = data_rows
        logger.info(f"Parsed sheet '{sheet_name}': {len(data_rows)} row(s)")

    wb.close()
    return result
