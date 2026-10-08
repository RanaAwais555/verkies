"""CSV parsing for discovery imports: limits, dialects, headers and the field guess."""

import pytest

from app.core.errors import ValidationFailed
from app.discovery import csv_import
from app.discovery.csv_import import csv_safe, guess_mapping, parse, validate_mapping


def test_semicolons_bom_blank_rows_and_ragged_rows() -> None:
    parsed = parse("﻿Company;Web site;Notes\nAcme;acme.com;hi\n\n;;\nBeta;beta.io\n")
    assert parsed.columns == ["Company", "Web site", "Notes"]
    assert parsed.rows == [
        {"Company": "Acme", "Web site": "acme.com", "Notes": "hi"},
        {"Company": "Beta", "Web site": "beta.io", "Notes": ""},
    ]


def test_quoted_commas_and_duplicate_or_blank_headers() -> None:
    parsed = parse('Name,Name,,URL\n"Acme, Inc.",x,y,https://acme.com\n')
    assert parsed.columns == ["Name", "Name (2)", "Column 3", "URL"]
    assert parsed.rows[0]["Name"] == "Acme, Inc."


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "empty"),
        ("Website\n", "no data"),
        ("x" * (csv_import.MAX_CHARS + 1), "2 MB"),
        (
            ",".join(f"c{i}" for i in range(csv_import.MAX_COLUMNS + 1)) + "\n1\n",
            "Too many columns",
        ),
        ("Website\n" + "a.com\n" * (csv_import.MAX_ROWS + 1), "rows"),
    ],
)
def test_limits_and_empty_files_are_refused(content: str, message: str) -> None:
    with pytest.raises(ValidationFailed, match=message):
        parse(content)


def test_long_cells_are_cut() -> None:
    parsed = parse("Notes,Website\n" + "x" * 5000 + ",a.com\n")
    assert len(parsed.rows[0]["Notes"]) == csv_import.MAX_CELL


def test_mapping_is_guessed_from_clear_headers_only() -> None:
    assert guess_mapping(["Company Name", "Homepage", "Sector", "Owner", "Country"]) == {
        "name": "Company Name",
        "website": "Homepage",
        "industry": "Sector",
        "country": "Country",
    }
    assert guess_mapping(["A", "B"]) == {}


def test_mapping_needs_a_website_column_that_exists() -> None:
    cols = ["Company", "URL"]
    assert validate_mapping({"website": "URL", "name": "", "notes": ""}, cols) == {"website": "URL"}
    with pytest.raises(ValidationFailed, match="website"):
        validate_mapping({"name": "Company"}, cols)
    with pytest.raises(ValidationFailed, match="No such column"):
        validate_mapping({"website": "Site"}, cols)
    with pytest.raises(ValidationFailed, match="Unknown fields"):
        validate_mapping({"website": "URL", "revenue": "Company"}, cols)


@pytest.mark.parametrize("value", ["=1+1", "+44 20", "-2", "@SUM(A1)", "\tx"])
def test_exported_cells_cannot_become_formulas(value: str) -> None:
    assert csv_safe(value) == f"'{value}"
    assert csv_safe("Acme") == "Acme" and csv_safe(None) == ""
