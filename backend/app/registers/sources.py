"""What every register source provides (slice 8.1): where to download it, how often, and how
to turn the download into entries. Adding a register is one new module and one line in
SOURCES; the refresh, the status page and the search work for all of them."""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.config import Settings
from app.providers.fetch.safe_http import SafeHttpFetcher

COMPANY_NUMBER = re.compile(r"^(?:[A-Z]{2}\d{6}|\d{8})$")
POSTCODE_AREA = re.compile(r"^([A-Z]{1,2})\d")
# Postcode areas wholly or mostly inside Greater London.
LONDON_AREAS = ("E", "EC", "N", "NW", "SE", "SW", "W", "WC")


@dataclass(frozen=True)
class RegisterEntry:
    """One organisation as a source lists it, in VROS's shape."""

    source_id: str
    name: str
    active: bool
    status: str | None = None
    legal_form: str | None = None
    company_number: str | None = None
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    postcode: str | None = None
    town: str | None = None
    postcode_areas: tuple[str, ...] = ()
    areas: tuple[str, ...] = ()
    office_count: int | None = None
    authorised_on: date | None = None
    data: dict[str, Any] = field(default_factory=dict)


class RegisterSourceAdapter(Protocol):
    key: str
    name: str
    publisher: str
    # Shown wherever the data is (the publisher's licence asks for it).
    attribution: str
    # How often the publisher updates it; the worker checks this often.
    cadence_hours: int

    def configured(self, settings: Settings) -> bool: ...

    async def download(self, fetcher: SafeHttpFetcher, settings: Settings) -> bytes: ...

    def parse(self, body: bytes) -> list[RegisterEntry]: ...


def company_number(raw: object) -> str | None:
    """ "oc338007" -> "OC338007", "1234567" -> "01234567"; anything else -> None."""
    value = re.sub(r"\s", "", str(raw or "")).upper()
    if value.isdigit() and len(value) < 8:
        value = value.zfill(8)
    return value if COMPANY_NUMBER.match(value) else None


def postcode_area(postcode: object) -> str | None:
    """ "SE15 4NL" -> "SE", "m1 1aa" -> "M"."""
    match = POSTCODE_AREA.match(str(postcode or "").strip().upper())
    return match.group(1) if match else None


def website(raw: object) -> str | None:
    """A register's website field as a homepage URL: "www.firm.co.uk" -> "https://www.firm.co.uk/".
    Values that are not a host name (an email address, free text) are dropped."""
    value = str(raw or "").strip()
    if not value or "@" in value or " " in value:
        return None
    value = re.sub(r"^https?://", "", value, flags=re.IGNORECASE).split("/")[0].strip(".").lower()
    if "." not in value or not re.fullmatch(r"[a-z0-9.-]+(:\d+)?", value):
        return None
    return f"https://{value}/"


def text(raw: object, limit: int) -> str | None:
    value = " ".join(str(raw or "").split())
    return value[:limit] or None
