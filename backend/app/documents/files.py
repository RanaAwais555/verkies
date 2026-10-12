"""What a document is, read from its own bytes (slice 4.4).

Only these kinds are accepted, and the file's name must agree with its contents:

- PDF (`%PDF-`), PNG, JPEG and WebP images, by their signatures;
- Word, Excel and PowerPoint (`.docx`, `.xlsx`, `.pptx`): a ZIP holding `[Content_Types].xml` and
  the part that kind of file must have; macro-enabled formats are refused;
- plain text, Markdown and CSV: UTF-8 with no NUL bytes.

Anything a browser could run (HTML, SVG, scripts) or a program is refused, and downloads are always
sent as attachments, so a file is never rendered by VROS itself.
"""

import io
import re
import unicodedata
import zipfile

from app.core.errors import ValidationFailed

OFFICE = {
    ".docx": (
        "word/document.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".xlsx": (
        "xl/workbook.xml",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    ".pptx": (
        "ppt/presentation.xml",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
}
TEXT = {".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv"}
IMAGES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
ACCEPTED = (".pdf", *IMAGES, *OFFICE, *TEXT)


def extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot > 0 else ""


def clean_filename(name: str) -> str:
    """The last path part, without control characters, at most 200 characters, keeping its
    extension. Only ever used to name a download."""
    base = re.split(r"[\\/]", name)[-1]
    base = "".join(
        c for c in unicodedata.normalize("NFC", base) if unicodedata.category(c)[0] != "C"
    )
    base = base.strip().strip(".") or "document"
    if len(base) > 200:
        ext = extension(base)
        base = base[: 200 - len(ext)] + ext
    return base


def _refuse(message: str) -> ValidationFailed:
    return ValidationFailed(message, code="unsupported_file")


def detect(data: bytes, filename: str) -> str:
    """The content type of an accepted file, or ValidationFailed."""
    ext = extension(filename)
    if ext not in ACCEPTED:
        raise _refuse(
            "VROS takes PDF, Word, Excel, PowerPoint, images (PNG, JPEG, WebP), text, "
            "Markdown and CSV files."
        )
    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise _refuse("That file is not a PDF.")
        return "application/pdf"
    if ext in IMAGES:
        is_png = data.startswith(b"\x89PNG\r\n\x1a\n")
        is_jpeg = data.startswith(b"\xff\xd8\xff")
        is_webp = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        expected = {"image/png": is_png, "image/jpeg": is_jpeg, "image/webp": is_webp}
        if not expected[IMAGES[ext]]:
            raise _refuse(f"That file is not a {ext[1:].upper()} image.")
        return IMAGES[ext]
    if ext in OFFICE:
        part, content_type = OFFICE[ext]
        if not data.startswith(b"PK\x03\x04"):
            raise _refuse(f"That file is not a {ext} document.")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile as exc:
            raise _refuse(f"That file is not a {ext} document.") from exc
        if "[Content_Types].xml" not in names or part not in names:
            raise _refuse(f"That file is not a {ext} document.")
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            raise _refuse("Files with macros are not accepted.")
        return content_type
    if b"\x00" in data:
        raise _refuse("That file is not plain text.")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _refuse("Text files must be UTF-8.") from exc
    return TEXT[ext]
