"""The Charity Commission's register of charities in England and Wales (slice 8.3).

The Commission publishes a daily extract as tab-separated text in zip files (Open Government
Licence). Two are read: the charities themselves and their classifications ("What" the charity
does: Education/training, Health...). Only registered main charities are kept (linked charities
and removed ones are left out, so a charity that is removed from the register is marked removed
here too). The files are large, so they are read row by row, never as a whole.
"""

import csv
import io
import sys
import zipfile
from collections.abc import Iterator
from datetime import date

from app.config import Settings
from app.providers.errors import ProviderError
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.registers.sources import (
    ZIP_TYPES,
    RegisterEntry,
    company_number,
    fetch,
    postcode_area,
    text,
    website,
)

BASE = "https://ccewuksprdoneregsadata1.blob.core.windows.net/data/txt/publicextract.{name}.zip"
FILES = ("charity", "charity_classification")
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def _rows(data: bytes) -> Iterator[dict[str, str]]:
    """Rows of the one tab-separated file inside an extract zip."""
    try:
        book = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ProviderError(
            "The Charity Commission sent no zip.", code="register_bad_output"
        ) from exc
    with book:
        names = [n for n in book.namelist() if n.endswith(".txt")]
        if not names:
            raise ProviderError("The extract has no text file.", code="register_bad_output")
        with book.open(names[0]) as raw:
            lines = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
            yield from csv.DictReader(lines, delimiter="\t", quoting=csv.QUOTE_NONE)


def _income(value: str) -> int | None:
    try:
        return round(float(value)) if value.strip() else None
    except ValueError:
        return None


def _town(row: dict[str, str]) -> str | None:
    """The last filled address line after the first: the extract's lines are free-form,
    and the town is the one written just before the postcode."""
    for n in (5, 4, 3, 2):
        if town := text(row.get(f"charity_contact_address{n}"), 120):
            return town
    return None


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


def classifications(data: bytes) -> dict[str, list[str]]:
    """Registered number -> what the charity does ("What" classifications only)."""
    found: dict[str, list[str]] = {}
    for row in _rows(data):
        if row.get("classification_type") != "What" or row.get("linked_charity_number") != "0":
            continue
        name = text(row.get("classification_description"), 120)
        number = (row.get("registered_charity_number") or "").strip()
        if name and number:
            found.setdefault(number, []).append(name)
    return found


def parse(charities: bytes, classified: bytes) -> list[RegisterEntry]:
    what = classifications(classified)
    entries: dict[str, RegisterEntry] = {}
    for row in _rows(charities):
        if (
            row.get("charity_registration_status") != "Registered"
            or row.get("linked_charity_number") != "0"
        ):
            continue
        number, name = (
            (row.get("registered_charity_number") or "").strip(),
            text(row.get("charity_name"), 300),
        )
        if not number or not name:
            continue
        postcode = text(row.get("charity_contact_postcode"), 12)
        area = postcode_area(postcode)
        entries.setdefault(
            number,
            RegisterEntry(
                source_id=number,
                name=name,
                active=True,
                status="Registered",
                legal_form=text(row.get("charity_type"), 80),
                company_number=company_number(row.get("charity_company_registration_number")),
                website=website(row.get("charity_contact_web")),
                phone=text(row.get("charity_contact_phone"), 40),
                email=text(row.get("charity_contact_email"), 320),
                postcode=postcode,
                town=_town(row),
                postcode_areas=(area,) if area else (),
                areas=tuple(what.get(number, [])),
                authorised_on=_date(row.get("date_of_registration") or ""),
                income=_income(row.get("latest_income") or ""),
                data={"activities": text(row.get("charity_activities"), 300)},
            ),
        )
    if not entries:
        raise ProviderError(
            "The extract listed no registered charities.", code="register_bad_output"
        )
    return list(entries.values())


class CharityRegister:
    key = "charity"
    short_name = "Charities"
    name = "Charity Commission (England and Wales)"
    publisher = "Charity Commission for England and Wales"
    attribution = (
        "Contains public sector information from the Charity Commission for England and "
        "Wales, licensed under the Open Government Licence v3.0."
    )
    cadence_hours = 24
    area_label = "What the charity does"
    has_location = True
    has_income = True
    has_offices = False
    specialist_areas: int | None = None

    def __init__(self, base: str = BASE) -> None:
        self.base = base

    def configured(self, settings: Settings) -> bool:
        return True

    async def download(self, fetcher: SafeHttpFetcher, settings: Settings) -> dict[str, bytes]:
        return {
            name: await fetch(fetcher, self.base.format(name=name), ZIP_TYPES, self.publisher)
            for name in FILES
        }

    def parse(self, files: dict[str, bytes]) -> list[RegisterEntry]:
        return parse(files["charity"], files["charity_classification"])
