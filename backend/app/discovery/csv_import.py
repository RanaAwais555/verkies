"""Reading an uploaded CSV safely: size limits, delimiter detection, a clean header row, and a
best guess at which column holds which field. Pure functions, no database."""

import csv
import io
import re
from dataclasses import dataclass

from app.core.errors import ValidationFailed

MAX_CHARS = 2_000_000
MAX_ROWS = 5_000
MAX_COLUMNS = 50
MAX_CELL = 2_000
DELIMITERS = (",", ";", "\t", "|")

FIELDS = ("website", "name", "country", "industry", "notes")
SYNONYMS: dict[str, tuple[str, ...]] = {
    "website": (
        "website",
        "url",
        "domain",
        "web",
        "site",
        "homepage",
        "company website",
        "web site",
    ),
    "name": (
        "company",
        "name",
        "company name",
        "organisation",
        "organization",
        "business",
        "account",
    ),
    "country": ("country", "country code", "hq country"),
    "industry": ("industry", "sector", "vertical", "category"),
    "notes": ("notes", "note", "comment", "comments", "description"),
}


@dataclass
class ParsedCsv:
    columns: list[str]
    rows: list[dict[str, str]]


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def parse(content: str) -> ParsedCsv:
    if len(content) > MAX_CHARS:
        raise ValidationFailed("The file is larger than 2 MB. Split it into smaller files.")
    content = content.lstrip("﻿")
    if not content.strip():
        raise ValidationFailed("The file is empty.")
    # The header row decides the delimiter: sniffing data rows fails on ragged files.
    first_line = content.splitlines()[0]
    counts = {d: first_line.count(d) for d in DELIMITERS}
    delimiter = max(counts, key=lambda d: counts[d]) if any(counts.values()) else ","
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise ValidationFailed("The file has no header row.") from exc
    if len(header) > MAX_COLUMNS:
        raise ValidationFailed(f"Too many columns ({len(header)}); the limit is {MAX_COLUMNS}.")
    columns: list[str] = []
    for i, raw in enumerate(header):
        name = raw.strip()[:120] or f"Column {i + 1}"
        base, n = name, 2
        while name in columns:
            name, n = f"{base} ({n})", n + 1
        columns.append(name)
    if not any(c for c in header if c.strip()):
        raise ValidationFailed("The first row must name the columns.")

    rows: list[dict[str, str]] = []
    try:
        for record in reader:
            if not any(cell.strip() for cell in record):
                continue
            if len(rows) >= MAX_ROWS:
                raise ValidationFailed(f"More than {MAX_ROWS} rows. Split the file.")
            rows.append(
                {
                    col: (record[i].strip()[:MAX_CELL] if i < len(record) else "")
                    for i, col in enumerate(columns)
                }
            )
    except csv.Error as exc:
        raise ValidationFailed(f"The file is not valid CSV: {exc}") from exc
    if not rows:
        raise ValidationFailed("The file has a header row but no data.")
    return ParsedCsv(columns, rows)


def guess_mapping(columns: list[str]) -> dict[str, str]:
    """Field -> column, for the columns whose header clearly names a field."""
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    for field in FIELDS:
        for column in columns:
            if column not in taken and _key(column) in SYNONYMS[field]:
                mapping[field] = column
                taken.add(column)
                break
    return mapping


def validate_mapping(mapping: dict[str, str], columns: list[str]) -> dict[str, str]:
    unknown_fields = set(mapping) - set(FIELDS)
    if unknown_fields:
        raise ValidationFailed(f"Unknown fields: {', '.join(sorted(unknown_fields))}.")
    clean = {f: c for f, c in mapping.items() if c}
    missing = {c for c in clean.values() if c not in columns}
    if missing:
        raise ValidationFailed(f"No such column: {', '.join(sorted(missing))}.")
    if "website" not in clean:
        raise ValidationFailed("Choose the column that holds each company's website.")
    return clean


def csv_safe(value: object) -> str:
    """A cell for an exported CSV, defused against spreadsheet formula injection."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text
