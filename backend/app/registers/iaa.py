"""The Immigration Advice Authority's list of regulated organisations (slice 8.3).

Published on GOV.UK as a spreadsheet released under Freedom of Information (Open Government
Licence): every organisation the IAA regulates, with its registration number, level, website and
first approval date. It has no addresses, so a location filter does not apply. A new release
replaces the file at a new URL; the publication page stays put.
"""

from datetime import date, timedelta

from app.config import Settings
from app.providers.errors import ProviderError
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.registers import xlsx
from app.registers.sources import XLSX_TYPES, RegisterEntry, fetch, govuk_attachment, text, website

PAGE = "government/publications/register-of-currently-registered-immigration-advice-organisations"
COLUMNS = {
    "name": "organisation name",
    "number": "organisation number",
    "level": "regulated level",
    "website": "organisation website",
    "approved": "earliest approval date",
}


def _date(value: str) -> date | None:
    value = value.strip()
    if value.replace(".", "", 1).isdigit():  # a spreadsheet serial day number
        return date(1899, 12, 30) + timedelta(days=int(float(value)))
    for parse in (date.fromisoformat, lambda v: date(int(v[6:10]), int(v[3:5]), int(v[:2]))):
        try:
            return parse(value[:10])
        except (ValueError, IndexError):
            continue
    return None


def parse(rows: list[list[str]]) -> list[RegisterEntry]:
    header_at = next(
        (i for i, r in enumerate(rows) if COLUMNS["name"] in [c.lower() for c in r]), None
    )
    if header_at is None:
        raise ProviderError("The IAA list has no header row.", code="register_bad_output")
    header = [c.strip().lower() for c in rows[header_at]]
    try:
        at = {key: header.index(label) for key, label in COLUMNS.items()}
    except ValueError as exc:
        raise ProviderError(
            "The IAA list's columns have changed.", code="register_bad_output"
        ) from exc
    entries: dict[str, RegisterEntry] = {}
    for row in rows[header_at + 1 :]:

        def cell(key: str, row: list[str] = row) -> str:
            return row[at[key]] if at[key] < len(row) else ""

        number, name = cell("number").strip(), text(cell("name"), 300)
        if not number or not name:
            continue
        level = text(cell("level"), 80)
        entries.setdefault(
            number,
            RegisterEntry(
                source_id=number,
                name=name,
                active=True,  # the list holds currently registered organisations only
                status=level,
                website=website(cell("website")),
                areas=(level,) if level else (),
                authorised_on=_date(cell("approved")),
            ),
        )
    return list(entries.values())


class IaaRegister:
    key = "iaa"
    short_name = "IAA"
    name = "Immigration Advice Authority"
    publisher = "Immigration Advice Authority"
    attribution = (
        "Contains public sector information from the Immigration Advice Authority, licensed "
        "under the Open Government Licence v3.0."
    )
    cadence_hours = 24 * 7  # released occasionally; checked weekly
    area_label = "Regulated level"
    has_location = False
    has_income = False
    has_offices = False
    specialist_areas: int | None = None

    def configured(self, settings: Settings) -> bool:
        return True

    async def download(self, fetcher: SafeHttpFetcher, settings: Settings) -> dict[str, bytes]:
        url = await govuk_attachment(fetcher, PAGE, ".xlsx", self.publisher)
        return {"organisations": await fetch(fetcher, url, XLSX_TYPES, self.publisher)}

    def parse(self, files: dict[str, bytes]) -> list[RegisterEntry]:
        return parse(xlsx.rows(files["organisations"]))
