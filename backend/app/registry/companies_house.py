"""Companies House public data API (PROVIDER_SPEC.md §3; free key from
developer.company-information.service.gov.uk). Looked up by registered number only: the number
comes from the company's own site (or Wikidata), never from a name search."""

import base64
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.fetch.safe_http import SafeHttpFetcher

API = "https://api.company-information.service.gov.uk"
PUBLIC_PAGE = "https://find-and-update.company-information.service.gov.uk/company/{number}"
NUMBER = re.compile(r"^(?:[A-Z]{2}\d{6}|\d{8})$")
INACTIVE = frozenset(
    {
        "dissolved",
        "liquidation",
        "receivership",
        "administration",
        "converted-closed",
        "insolvency-proceedings",
        "removed",
        "closed",
    }
)
DECIDING_ROLES = {
    "director": "Director",
    "llp-designated-member": "Designated member",
    "llp-member": "Member",
    "corporate-director": "Corporate director",
}
MAX_OFFICERS = 10


@dataclass(frozen=True)
class CompanyRecord:
    number: str
    name: str
    status: str
    incorporated: date | None
    company_type: str | None
    sic_codes: list[str] = field(default_factory=list)
    locality: str | None = None
    postal_code: str | None = None

    @property
    def active(self) -> bool:
        return self.status not in INACTIVE


@dataclass(frozen=True)
class Officer:
    name: str
    role: str
    appointed: date | None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def parse_company(data: Any) -> CompanyRecord:
    if not isinstance(data, dict) or not data.get("company_number") or not data.get("company_name"):
        raise ProviderError("Companies House returned no company.", code="registry_bad_output")
    office = data.get("registered_office_address") or {}
    return CompanyRecord(
        number=str(data["company_number"]),
        name=" ".join(str(data["company_name"]).split()),
        status=str(data.get("company_status") or "unknown"),
        incorporated=_date(data.get("date_of_creation")),
        company_type=data.get("type"),
        sic_codes=[str(c) for c in data.get("sic_codes") or []][:6],
        locality=office.get("locality"),
        postal_code=office.get("postal_code"),
    )


def display_name(raw: str) -> str:
    """ "HART, Amelia Jane" -> "Amelia Jane Hart" (Companies House lists surname first)."""
    surname, _, given = raw.partition(",")
    parts = [given.strip(), surname.strip().title() if surname.isupper() else surname.strip()]
    return " ".join(p for p in parts if p) or raw.strip()


def parse_officers(data: Any) -> list[Officer]:
    """Current officers with a deciding role (directors, LLP members); resigned ones skipped."""
    items = data.get("items") if isinstance(data, dict) else None
    out: list[Officer] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("resigned_on"):
            continue
        role = DECIDING_ROLES.get(str(item.get("officer_role")))
        name = str(item.get("name") or "").strip()
        if role and name:
            out.append(Officer(display_name(name), role, _date(item.get("appointed_on"))))
        if len(out) >= MAX_OFFICERS:
            break
    return out


class CompaniesHouse:
    def __init__(self, api_key: str | None, *, base_url: str = API) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def _get(self, fetcher: SafeHttpFetcher, path: str) -> Any:
        if not self.api_key:
            raise ProviderUnavailable("Companies House is not configured (no API key).")
        token = base64.b64encode(f"{self.api_key}:".encode()).decode()
        result = await fetcher.fetch(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
            content_types=frozenset({"application/json"}),
        )
        if result.status == 404:
            raise ProviderError("Not on the Companies House register.", code="registry_not_found")
        if result.status in (401, 403):
            raise ProviderUnavailable("Companies House refused the API key.")
        if result.status != 200:
            raise ProviderError(f"Companies House returned {result.status}.", code="registry_error")
        try:
            return json.loads(result.body)
        except ValueError as exc:
            raise ProviderError(
                "Companies House returned invalid JSON.", code="registry_bad_output"
            ) from exc

    async def company(self, fetcher: SafeHttpFetcher, number: str) -> CompanyRecord:
        if not NUMBER.match(number):
            raise ProviderError(
                f"Not a Companies House number: {number}", code="registry_bad_input"
            )
        return parse_company(await self._get(fetcher, f"/company/{number}"))

    async def officers(self, fetcher: SafeHttpFetcher, number: str) -> list[Officer]:
        return parse_officers(
            await self._get(fetcher, f"/company/{number}/officers?items_per_page=35")
        )
