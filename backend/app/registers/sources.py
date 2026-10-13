"""What every register source provides (slice 8.1): where to download it, how often, and how
to turn the download into entries. Adding a register is one new module and one line in
SOURCES; the refresh, the status page and the search work for all of them."""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.config import Settings
from app.providers.errors import ProviderError
from app.providers.fetch.safe_http import SafeHttpFetcher

COMPANY_NUMBER = re.compile(r"^(?:[A-Z]{2}\d{6}|\d{8})$")
POSTCODE_AREA = re.compile(r"^([A-Z]{1,2})\d")
JSON_TYPES = frozenset({"application/json"})
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
    # Latest annual income in pounds, where the register states it (charities).
    income: int | None = None
    data: dict[str, Any] = field(default_factory=dict)


class RegisterSourceAdapter(Protocol):
    key: str
    name: str
    short_name: str  # in discovery job titles, e.g. "SRA", "Charities"
    publisher: str
    # Shown wherever the data is (the publisher's licence asks for it).
    attribution: str
    # How often the publisher updates it; the worker checks this often.
    cadence_hours: int
    # What the register's own categories are called on the search form ("Area of work").
    area_label: str
    # Whether entries carry postcodes, so a location filter means something.
    has_location: bool
    # Whether entries carry an annual income, so an income filter means something.
    has_income: bool
    # Whether entries carry an office count, so an offices filter means something.
    has_offices: bool
    # Organisations listing at most this many categories count as specialists (None: no such
    # filter for this register).
    specialist_areas: int | None

    def configured(self, settings: Settings) -> bool: ...

    async def download(self, fetcher: SafeHttpFetcher, settings: Settings) -> dict[str, bytes]:
        """The register's files by name (most registers are one file; some publish several)."""
        ...

    def parse(self, files: dict[str, bytes]) -> list[RegisterEntry]: ...


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


GOVUK_CONTENT = "https://www.gov.uk/api/content/{path}"
ZIP_TYPES = frozenset(
    {"application/zip", "application/x-zip-compressed", "application/octet-stream"}
)
CSV_TYPES = frozenset({"text/csv", "application/octet-stream", "text/plain"})
XLSX_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    }
)


async def fetch(fetcher: SafeHttpFetcher, url: str, types: frozenset[str], publisher: str) -> bytes:
    result = await fetcher.fetch(url, content_types=types)
    if result.status != 200:
        raise ProviderError(f"{publisher} returned {result.status}.", code="register_error")
    return result.body


async def govuk_attachment(fetcher: SafeHttpFetcher, path: str, suffix: str, publisher: str) -> str:
    """The current file behind a GOV.UK publication page (its URL changes with every release,
    the page's does not): the first attachment whose URL ends with `suffix`."""
    body = await fetch(fetcher, GOVUK_CONTENT.format(path=path), JSON_TYPES, "GOV.UK")
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise ProviderError("GOV.UK returned invalid JSON.", code="register_bad_output") from exc
    attachments = (data.get("details") or {}).get("attachments") or []
    for item in attachments:
        url = str(item.get("url") or "") if isinstance(item, dict) else ""
        if url.lower().endswith(suffix):
            return url
    raise ProviderError(
        f"{publisher}'s GOV.UK page has no {suffix} file.", code="register_bad_output"
    )
