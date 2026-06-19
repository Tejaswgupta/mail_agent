"""Detect airline carrier and normalize passenger manifest xlsx/xls to a unified schema.

Supported carriers and their source formats:
  6E  IndiGo        – .xlsx, 35 cols, title row + header row
  IX  Air India Exp – .xls,  43 cols, header row only
  TG  Thai Airways  – .xls,  24 cols, header row only
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import openpyxl
from loguru import logger

try:
    import xlrd  # type: ignore
    _XLRD_AVAILABLE = True
except ImportError:
    _XLRD_AVAILABLE = False

# Excel epoch for serial-date conversion (xlrd uses 1900 by default)
_XL_EPOCH = datetime.date(1899, 12, 30)


def _coerce_date(val: Any) -> str | None:
    """Convert an Excel serial float or various string formats to ISO date string."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return None
    if isinstance(val, (int, float)):
        try:
            return (_XL_EPOCH + datetime.timedelta(days=int(val))).isoformat()
        except (OverflowError, ValueError):
            return None
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.date().isoformat() if isinstance(val, datetime.datetime) else val.isoformat()
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(s.split(" ")[0].split("T")[0], fmt).date().isoformat()
        except ValueError:
            continue
    return s or None


# ── Column maps (source header → unified field) ───────────────────────────────

_INDIGO_MAP: dict[str, str] = {
    "Flight Number":          "flight_number",
    "Flight Date":            "flight_date",
    "Origin Airport":         "origin",
    "Destination Airport":    "destination",
    "PNR":                    "pnr",
    "First Name":             "first_name",
    "Last Name":              "last_name",
    "Passenger Type":         "passenger_type",
    "Gender":                 "gender",
    "Nationality":            "nationality",
    "Passport No":            "passport_number",
    "Class of Travel(6E)":    "cabin_class",
    "Seat Number":            "seat_number",
    "No. of Bags":            "no_of_bags",
    "Baggage Weight (in kgs)":"baggage_weight",
    "Email Address":          "email",
    "Contact Number":         "phone",
    "Date of Booking":        "booking_date",
}

_AIX_MAP: dict[str, str] = {
    "FlightNumber":           "flight_number",
    "CarrierCode":            "_carrier_code",  # merged into flight_number post-mapping
    "DepartureDate":          "flight_date",
    "RecordLocator":          "pnr",
    "Title":                  "title",
    "BookingPerson1stName":   "first_name",
    "BookingPersonLastName":  "last_name",
    "PaxType":                "passenger_type",
    "Pax_DOB":                "date_of_birth",
    "passenger_nationality":  "nationality",
    "PPNo":                   "passport_number",
    "SeatNumber":             "seat_number",
    "ProductClassCode":       "cabin_class",
    "BaggageCount":           "no_of_bags",
    "weight":                 "baggage_weight",
    "Email":                  "email",
    "HomePhone":              "phone",
}

_TG_MAP: dict[str, str] = {
    "FLIGHT NUMBER":                              "flight_number",
    "OPERATION DATE":                             "flight_date",
    "EMBARK":                                     "origin",
    "DISEMBARK":                                  "destination",
    "PNR":                                        "pnr",
    "PAX LAST NAME":                              "last_name",
    "PAX FULL NAME":                              "full_name",
    "PHONE":                                      "phone",
    "EMAIL":                                      "email",
    "TRAVEL DOCUMENT NUMBER":                     "passport_number",
    "DATE OF BIRTH":                              "date_of_birth",
    "NATIONALITY":                                "nationality",
    "TICKET NO":                                  "ticket_number",
    "TICKET ISSUE DATE":                          "ticket_issue_date",
    "CABIN CLASS":                                "cabin_class",
    "SEAT NO":                                    "seat_number",
    "NO OF BAGS":                                 "no_of_bags",
    "BAGGAGE WEIGHT":                             "baggage_weight",
    "MODE OF PAYMENT (INCLUDE LAST 4 DIGIT OF CREDIT CARD USED)": "payment_mode",
}

_CARRIER_MAPS = {"6E": _INDIGO_MAP, "IX": _AIX_MAP, "TG": _TG_MAP}


# ── Carrier + manifest type detection ────────────────────────────────────────

def _detect_carrier(filename: str, headers: list[str]) -> str | None:
    header_set = set(headers)
    name_up = filename.upper()

    # Header-based detection is more reliable than filename
    if "RecordLocator" in header_set:
        return "IX"
    if "PAX FULL NAME" in header_set or "EMBARK" in header_set:
        return "TG"
    if "Class of Travel(6E)" in header_set or "Origin Airport" in header_set:
        return "6E"

    # Fall back to filename
    if "IX" in name_up and ("MCT" in name_up or "BOM" in name_up or "MANIFEST" in name_up):
        return "IX"
    if name_up.startswith("TG") or "PRE-TG" in name_up or "-TG" in name_up:
        return "TG"
    if "6E" in name_up or name_up.startswith("PREDEP_6E"):
        return "6E"

    return None


def _detect_manifest_type(carrier: str, filename: str, title_text: str | None) -> str:
    name_up = filename.upper()
    if carrier == "6E" and title_text:
        return "pre_departure" if "PRE-DEPARTURE" in title_text.upper() else "post_departure"
    if "PREDEP" in name_up or name_up.startswith("PRE-"):
        return "pre_departure"
    return "post_departure"


# ── File readers ──────────────────────────────────────────────────────────────

def _read_xlsx(path: Path) -> tuple[str | None, list[str], list[dict]]:
    """Return (title_text_or_None, headers, raw_row_dicts)."""
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not all_rows:
        return None, [], []

    # IndiGo files have a single-cell title as row 0
    title_text: str | None = None
    header_start = 0
    first_nonempty = [v for v in all_rows[0] if v is not None]
    if len(first_nonempty) == 1 or (first_nonempty and str(first_nonempty[0]).startswith("Airline:")):
        title_text = str(first_nonempty[0]) if first_nonempty else None
        header_start = 1

    if header_start >= len(all_rows):
        return title_text, [], []

    headers = [str(h).strip() if h is not None else "" for h in all_rows[header_start]]

    data_rows = []
    for row in all_rows[header_start + 1:]:
        if all(c is None for c in row):
            continue
        data_rows.append(dict(zip(headers, row)))

    return title_text, headers, data_rows


def _read_xls(path: Path) -> tuple[str | None, list[str], list[dict]]:
    """Return (title_text_or_None, headers, raw_row_dicts). Requires xlrd<2."""
    if not _XLRD_AVAILABLE:
        raise ImportError("xlrd<2 is required to read .xls files — pip install 'xlrd<2'")

    wb = xlrd.open_workbook(str(path))
    ws = wb.sheet_by_index(0)

    if ws.nrows == 0:
        return None, [], []

    title_text: str | None = None
    header_start = 0
    first_row = [ws.cell_value(0, c) for c in range(ws.ncols)]
    non_empty = [v for v in first_row if v != "" and v is not None]
    if len(non_empty) == 1 or (non_empty and str(non_empty[0]).startswith("Airline:")):
        title_text = str(non_empty[0]) if non_empty else None
        header_start = 1

    if header_start >= ws.nrows:
        return title_text, [], []

    headers = [str(ws.cell_value(header_start, c)).strip() for c in range(ws.ncols)]

    data_rows = []
    for row_idx in range(header_start + 1, ws.nrows):
        row = [ws.cell_value(row_idx, c) for c in range(ws.ncols)]
        if all(v == "" or v is None for v in row):
            continue
        data_rows.append(dict(zip(headers, row)))

    return title_text, headers, data_rows


# ── Row normalization ─────────────────────────────────────────────────────────

_DATE_FIELDS = {"flight_date", "date_of_birth", "booking_date", "ticket_issue_date"}


def _normalize_row(raw: dict, col_map: dict[str, str], carrier: str) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for src, dst in col_map.items():
        val = raw.get(src)
        # Treat whitespace-only strings as absent
        if isinstance(val, str):
            val = val.strip() or None
        if val is None or val == "":
            continue
        if dst in _DATE_FIELDS:
            val = _coerce_date(val)
        if val is not None:
            row[dst] = val

    if carrier == "IX":
        carrier_code = row.pop("_carrier_code", "IX")
        fn = row.get("flight_number", "")
        if fn and not str(fn).startswith(str(carrier_code)):
            row["flight_number"] = f"{carrier_code}{int(fn) if isinstance(fn, float) else fn}"

    row["airline_code"] = carrier
    return row


# ── Public API ────────────────────────────────────────────────────────────────

def normalize(path: Path) -> tuple[str, str, list[dict[str, Any]]] | None:
    """Detect carrier and return normalized passenger rows.

    Returns ``(airline_code, manifest_type, rows)`` where each row is a dict
    of unified fields plus a ``"_raw"`` key holding the original source values.
    Returns ``None`` if the file is not recognized as a passenger manifest.
    """
    suffix = path.suffix.lower()
    try:
        if suffix == ".xlsx":
            title_text, headers, raw_rows = _read_xlsx(path)
        elif suffix == ".xls":
            title_text, headers, raw_rows = _read_xls(path)
        else:
            return None
    except Exception as exc:
        logger.warning(f"manifest_normalizer: cannot read {path.name}: {exc}")
        return None

    carrier = _detect_carrier(path.name, headers)
    if carrier is None:
        logger.debug(f"manifest_normalizer: unrecognized carrier in {path.name}")
        return None

    manifest_type = _detect_manifest_type(carrier, path.name, title_text)
    col_map = _CARRIER_MAPS[carrier]

    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        normalized = _normalize_row(raw, col_map, carrier)
        normalized["_raw"] = raw
        rows.append(normalized)

    logger.info(
        f"manifest_normalizer: {path.name} → {carrier} / {manifest_type} / {len(rows)} row(s)"
    )
    return carrier, manifest_type, rows
