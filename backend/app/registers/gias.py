"""Get Information About Schools, the Department for Education's register of every school and
college in England (slice 8.3).

A daily CSV of all establishments, open and closed (Open Government Licence). The file is named
by its date and is not always ready early in the day, so the last three days are tried in turn.
Head teachers' names are kept as published, as the school's named contact.
"""

import csv
import io
from datetime import UTC, date, datetime, timedelta

from app.config import Settings
from app.providers.errors import ProviderError
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.fetch.types import UNTYPED
from app.registers.sources import (
    CSV_TYPES,
    RegisterEntry,
    fetch,
    postcode_area,
    text,
    website,
)

URL = (
    "https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/edubasealldata{day}.csv"
)
DAYS_TRIED = 3
# The DfE file server sends no Content-Type, so this fixed URL accepts an untyped response.
TYPES = CSV_TYPES | {UNTYPED}


def _date(value: str) -> date | None:
    try:  # dd-mm-yyyy
        return date(int(value[6:10]), int(value[3:5]), int(value[:2]))
    except (ValueError, IndexError):
        return None


def _int(value: str) -> int | None:
    return int(value) if value.strip().isdigit() else None


def parse(body: bytes) -> list[RegisterEntry]:
    # Decoded as it is read, not copied into one string first (the file is 60MB+).
    lines = io.TextIOWrapper(io.BytesIO(body), encoding="cp1252", errors="replace", newline="")
    reader = csv.DictReader(lines)
    if not reader.fieldnames or "URN" not in reader.fieldnames:
        raise ProviderError("The schools file has no URN column.", code="register_bad_output")
    entries: dict[str, RegisterEntry] = {}
    for row in reader:
        urn, name = (row.get("URN") or "").strip(), text(row.get("EstablishmentName"), 300)
        if not urn or not name:
            continue
        group = text(row.get("EstablishmentTypeGroup (name)"), 120)
        phase = text(row.get("PhaseOfEducation (name)"), 120)
        head = " ".join(
            p for p in (row.get("HeadFirstName"), row.get("HeadLastName")) if p and p.strip()
        )
        postcode = text(row.get("Postcode"), 12)
        area = postcode_area(postcode)
        entries.setdefault(
            urn,
            RegisterEntry(
                source_id=urn,
                name=name,
                active=row.get("EstablishmentStatus (name)") == "Open",
                status=text(row.get("EstablishmentStatus (name)"), 80),
                legal_form=text(row.get("TypeOfEstablishment (name)"), 80),
                website=website(row.get("SchoolWebsite")),
                phone=text(row.get("TelephoneNum"), 40),
                postcode=postcode,
                town=text(row.get("Town"), 120),
                postcode_areas=(area,) if area else (),
                areas=tuple(a for a in (group, phase) if a and a != "Not applicable"),
                authorised_on=_date(row.get("OpenDate") or ""),
                data={
                    "head": {
                        "title": text(row.get("HeadTitle (name)"), 40),
                        "name": text(head, 120),
                        "job_title": text(row.get("HeadPreferredJobTitle"), 80),
                    }
                    if head
                    else None,
                    "pupils": _int(row.get("NumberOfPupils") or ""),
                    "local_authority": text(row.get("LA (name)"), 120),
                },
            ),
        )
    return list(entries.values())


class SchoolsRegister:
    key = "gias"
    short_name = "Schools"
    name = "Schools in England (GIAS)"
    publisher = "Department for Education"
    attribution = (
        "Contains public sector information from the Department for Education's Get "
        "Information About Schools, licensed under the Open Government Licence v3.0."
    )
    cadence_hours = 24
    area_label = "School type"
    has_location = True
    has_income = False
    has_offices = False
    specialist_areas: int | None = None

    def __init__(self, url: str = URL) -> None:
        self.url = url

    def configured(self, settings: Settings) -> bool:
        return True

    async def download(self, fetcher: SafeHttpFetcher, settings: Settings) -> dict[str, bytes]:
        today = datetime.now(UTC).date()
        last: ProviderError | None = None
        for back in range(DAYS_TRIED):
            day = (today - timedelta(days=back)).strftime("%Y%m%d")
            try:
                return {
                    "establishments": await fetch(
                        fetcher, self.url.format(day=day), TYPES, self.publisher
                    )
                }
            except ProviderError as exc:
                last = exc
        raise last or ProviderError("No schools file found.", code="register_error")

    def parse(self, files: dict[str, bytes]) -> list[RegisterEntry]:
        return parse(files["establishments"])
