"""Slice 4.4: what a document is, from its own bytes."""

import io
import zipfile

import pytest

from app.core.errors import ValidationFailed
from app.documents.files import clean_filename, detect


def office(*parts: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for part in parts:
            archive.writestr(part, "<x/>")
    return out.getvalue()


@pytest.mark.parametrize(
    ("name", "data", "content_type"),
    [
        ("proposal.pdf", b"%PDF-1.7\n...", "application/pdf"),
        ("shot.PNG", b"\x89PNG\r\n\x1a\n....", "image/png"),
        ("photo.jpeg", b"\xff\xd8\xff\xe0....", "image/jpeg"),
        ("photo.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        ("notes.md", "# Kick-off\nAgreed scope, phase one \u2013 done".encode(), "text/markdown"),
        ("export.csv", b"name,value\nacme,1\n", "text/csv"),
        (
            "sow.docx",
            office("[Content_Types].xml", "word/document.xml"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "plan.xlsx",
            office("[Content_Types].xml", "xl/workbook.xml"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ],
)
def test_accepted_files(name: str, data: bytes, content_type: str) -> None:
    assert detect(data, name) == content_type


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("page.html", b"<html><script>alert(1)</script></html>"),
        ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>"),
        ("setup.exe", b"MZ\x90\x00"),
        ("no-extension", b"%PDF-1.7"),
        ("fake.pdf", b"<html>not a pdf</html>"),
        ("fake.png", b"\xff\xd8\xff\xe0 a jpeg"),
        ("fake.docx", office("[Content_Types].xml", "xl/workbook.xml")),
        ("broken.docx", b"PK\x03\x04 not really a zip"),
        ("macros.docx", office("[Content_Types].xml", "word/document.xml", "word/vbaProject.bin")),
        ("binary.txt", b"text\x00with a nul"),
        ("latin1.txt", "caf\u00e9".encode("latin-1")),
    ],
)
def test_refused_files(name: str, data: bytes) -> None:
    with pytest.raises(ValidationFailed):
        detect(data, name)


def test_filenames_are_cleaned() -> None:
    assert clean_filename("C:\\Users\\me\\Proposal v2.pdf") == "Proposal v2.pdf"
    assert clean_filename("../../etc/passwd") == "passwd"
    assert clean_filename("bad\x00\nname.pdf") == "badname.pdf"
    assert clean_filename("...") == "document"
    long = clean_filename("a" * 300 + ".pdf")
    assert len(long) == 200 and long.endswith(".pdf")
