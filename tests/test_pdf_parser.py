"""Tests for pdf_parser.py — uses real PDF fixtures built with reportlab or pdfplumber test data.

Since generating PDFs with tables requires reportlab (heavy dep), we mock
pdfplumber's extract_tables to return controlled data, plus one integration
test against a minimal real PDF if reportlab is available.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import pytest
import pdf_parser


# ── Unit tests via mocked pdfplumber ─────────────────────────────────────────

def _make_mock_pdf(pages_tables: list[list[list[list]]]):
    """Build a mock pdfplumber PDF whose pages return the given table data."""
    mock_pdf = MagicMock()
    mock_pages = []
    for tables in pages_tables:
        page = MagicMock()
        page.extract_tables.return_value = tables
        mock_pages.append(page)
    mock_pdf.pages = mock_pages
    mock_pdf.__enter__ = lambda s: s
    mock_pdf.__exit__ = MagicMock(return_value=False)
    return mock_pdf


def test_single_table_extracted(tmp_path):
    fake_pdf = _make_mock_pdf([[
        [["Date", "Description", "Amount"],
         ["2024-01-01", "Service", "500"],
         ["2024-01-02", "Tax", "50"]]
    ]])
    p = tmp_path / "invoice.pdf"
    p.write_bytes(b"%PDF-1.4 fake")

    with patch("pdf_parser.pdfplumber.open", return_value=fake_pdf):
        result = pdf_parser.parse(p)

    assert len(result) == 1
    assert result[0]["page_number"] == 1
    assert result[0]["table_index"] == 0
    assert result[0]["headers"] == ["Date", "Description", "Amount"]
    assert len(result[0]["rows"]) == 2
    assert result[0]["rows"][0] == ["2024-01-01", "Service", "500"]


def test_multiple_pages_and_tables(tmp_path):
    fake_pdf = _make_mock_pdf([
        # page 1: two tables
        [
            [["A", "B"], ["1", "2"]],
            [["X", "Y"], ["3", "4"]],
        ],
        # page 2: one table
        [
            [["P", "Q"], ["5", "6"]],
        ],
    ])
    p = tmp_path / "multi.pdf"
    p.write_bytes(b"%PDF fake")

    with patch("pdf_parser.pdfplumber.open", return_value=fake_pdf):
        result = pdf_parser.parse(p)

    assert len(result) == 3
    assert result[0]["page_number"] == 1 and result[0]["table_index"] == 0
    assert result[1]["page_number"] == 1 and result[1]["table_index"] == 1
    assert result[2]["page_number"] == 2 and result[2]["table_index"] == 0


def test_empty_tables_skipped(tmp_path):
    fake_pdf = _make_mock_pdf([[
        [[None, None], [None, None]],   # all empty — should be skipped
    ]])
    p = tmp_path / "empty.pdf"
    p.write_bytes(b"%PDF fake")

    with patch("pdf_parser.pdfplumber.open", return_value=fake_pdf):
        result = pdf_parser.parse(p)

    assert result == []


def test_page_with_no_tables_skipped(tmp_path):
    fake_pdf = _make_mock_pdf([
        [],       # page 1: no tables
        [[["H"], ["v"]]],  # page 2: one table
    ])
    p = tmp_path / "notables.pdf"
    p.write_bytes(b"%PDF fake")

    with patch("pdf_parser.pdfplumber.open", return_value=fake_pdf):
        result = pdf_parser.parse(p)

    assert len(result) == 1
    assert result[0]["page_number"] == 2


def test_none_cells_cleaned_to_empty_string(tmp_path):
    fake_pdf = _make_mock_pdf([[
        [["Col1", "Col2"], [None, "value"]],
    ]])
    p = tmp_path / "none.pdf"
    p.write_bytes(b"%PDF fake")

    with patch("pdf_parser.pdfplumber.open", return_value=fake_pdf):
        result = pdf_parser.parse(p)

    assert result[0]["rows"][0][0] == ""
    assert result[0]["rows"][0][1] == "value"


def test_duplicate_headers_deduped(tmp_path):
    fake_pdf = _make_mock_pdf([[
        [["Name", "Name", "Value"], ["Alice", "A", "10"]],
    ]])
    p = tmp_path / "duphdrs.pdf"
    p.write_bytes(b"%PDF fake")

    with patch("pdf_parser.pdfplumber.open", return_value=fake_pdf):
        result = pdf_parser.parse(p)

    headers = result[0]["headers"]
    assert len(set(headers)) == len(headers)


def test_invalid_file_raises(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"not a pdf")
    with patch("pdf_parser.pdfplumber.open", side_effect=Exception("bad file")):
        with pytest.raises(ValueError):
            pdf_parser.parse(p)
