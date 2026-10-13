"""A minimal reader for the first rows of an .xlsx sheet (slice 8.3): registers published as
spreadsheets, such as the IAA's, need nothing more than cell text.

An .xlsx file is a zip of XML parts. Only the shared strings and one worksheet are read, every
part is size-capped before it is parsed, and formulas, styles and dates are not interpreted
(dates come back as the spreadsheet's serial number, which callers convert).
"""

import io
import re
import zipfile
from xml.etree import ElementTree

from app.providers.errors import ProviderError

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
MAX_PART_BYTES = 200 * 1024 * 1024
CELL_REF = re.compile(r"([A-Z]+)")


def _xml(data: bytes) -> ElementTree.Element:
    """Parse one part. ElementTree never fetches external entities or DTDs, and the expat it
    uses caps entity expansion (no "billion laughs"); every part is size-capped before this."""
    return ElementTree.fromstring(data)  # noqa: S314 - see the docstring


def _part(book: zipfile.ZipFile, name: str) -> bytes | None:
    try:
        info = book.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_PART_BYTES:
        raise ProviderError(f"{name} is too large to read.", code="register_bad_output")
    return book.read(name)


def _column(ref: str) -> int:
    letters = CELL_REF.match(ref)
    index = 0
    for char in letters.group(1) if letters else "A":
        index = index * 26 + ord(char) - 64
    return index - 1


def _sheet_path(book: zipfile.ZipFile, sheet: str | None) -> str:
    """The worksheet part for a sheet name (or the first sheet)."""
    workbook = _part(book, "xl/workbook.xml")
    rels = _part(book, "xl/_rels/workbook.xml.rels")
    if workbook is None or rels is None:
        raise ProviderError("Not a spreadsheet.", code="register_bad_output")
    sheets = _xml(workbook).iter(f"{NS}sheet")
    chosen = next((s for s in sheets if sheet is None or s.get("name") == sheet), None)
    if chosen is None:
        raise ProviderError(f"The spreadsheet has no sheet {sheet!r}.", code="register_bad_output")
    rel_id = chosen.get(f"{REL_NS}id")
    for rel in _xml(rels):
        if rel.get("Id") == rel_id:
            target = str(rel.get("Target") or "").lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise ProviderError("The spreadsheet's sheet cannot be found.", code="register_bad_output")


def rows(data: bytes, sheet: str | None = None) -> list[list[str]]:
    """Every row of the sheet as cell text, empty cells as ""."""
    try:
        book = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ProviderError("Not a spreadsheet.", code="register_bad_output") from exc
    with book:
        shared: list[str] = []
        strings = _part(book, "xl/sharedStrings.xml")
        if strings is not None:
            for item in _xml(strings).iter(f"{NS}si"):
                shared.append("".join(t.text or "" for t in item.iter(f"{NS}t")))
        body = _part(book, _sheet_path(book, sheet))
        if body is None:
            raise ProviderError("The spreadsheet's sheet is missing.", code="register_bad_output")
        out: list[list[str]] = []
        for row in _xml(body).iter(f"{NS}row"):
            cells: dict[int, str] = {}
            for cell in row.iter(f"{NS}c"):
                kind = cell.get("t")
                if kind == "inlineStr":
                    text = "".join(t.text or "" for t in cell.iter(f"{NS}t"))
                else:
                    value = cell.find(f"{NS}v")
                    text = value.text or "" if value is not None else ""
                    if kind == "s" and text.isdigit() and int(text) < len(shared):
                        text = shared[int(text)]
                cells[_column(cell.get("r") or "A")] = text.strip()
            if cells:
                out.append([cells.get(i, "") for i in range(max(cells) + 1)])
        return out
