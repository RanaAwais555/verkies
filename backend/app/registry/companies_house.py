"""Companies House public data API (PROVIDER_SPEC.md §3; free key from
developer.company-information.service.gov.uk). Looked up by registered number only: the number
comes from the company's own site (or Wikidata), never from a name search."""

import base64
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlencode

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
    has_insolvency_history: bool = False

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
        has_insolvency_history=bool(data.get("has_insolvency_history")),
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


# Filed accounts type -> size band (Companies Act thresholds decide which a company may file).
ACCOUNTS_SIZE = {
    "micro-entity": "micro",
    "total-exemption-small": "small",
    "total-exemption-full": "small",
    "small": "small",
    "abridged": "small",
    "unaudited-abridged": "small",
    "audit-exemption-subsidiary": "small",
    "medium": "medium",
    "full": "full",
    "group": "group",
    "dormant": "dormant",
}
EVENT_WINDOW_DAYS = 365


@dataclass(frozen=True)
class AccountsInfo:
    accounts_type: str
    size_band: str | None
    made_up_to: date | None
    filed: date | None


@dataclass(frozen=True)
class FilingEvent:
    signal: str  # new_leader, rebrand, funding, financing
    title: str
    filed: date


@dataclass(frozen=True)
class Owner:
    name: str
    natures: tuple[str, ...]
    notified: date | None


@dataclass(frozen=True)
class RegistryCompany:
    number: str
    name: str
    status: str
    incorporated: date | None
    locality: str | None
    postal_code: str | None
    sic_codes: tuple[str, ...]


def _accounts_type(description: str) -> str | None:
    prefix = "accounts-with-accounts-type-"
    return description[len(prefix) :] if description.startswith(prefix) else None


def _event(item: dict[str, Any]) -> FilingEvent | None:
    category = str(item.get("category") or "")
    description = str(item.get("description") or "")
    values = item.get("description_values") or {}
    filed = _date(item.get("date"))
    if filed is None:
        return None
    if category == "officers" and description.startswith("appointment-of-director"):
        who = values.get("officer_name")
        title = f"Director appointed{f': {who}' if who else ''}"
        return FilingEvent("new_leader", title, filed)
    if category == "change-of-name":
        return FilingEvent("rebrand", "Change of company name filed", filed)
    if category == "capital" and "allotment" in description:
        return FilingEvent("funding", "New shares allotted", filed)
    if category == "mortgage" and description.startswith("mortgage-create"):
        return FilingEvent("financing", "Charge (secured lending) registered", filed)
    return None


def parse_filings(data: Any, today: date) -> tuple[AccountsInfo | None, list[FilingEvent]]:
    """The latest filed accounts and, from the last year, the filings that signal change."""
    items = data.get("items") if isinstance(data, dict) else None
    accounts: AccountsInfo | None = None
    events: list[FilingEvent] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        kind = _accounts_type(str(item.get("description") or ""))
        if accounts is None and item.get("category") == "accounts" and kind:
            values = item.get("description_values") or {}
            accounts = AccountsInfo(
                kind,
                ACCOUNTS_SIZE.get(kind),
                _date(values.get("made_up_date")),
                _date(item.get("date")),
            )
        event = _event(item)
        if event and (today - event.filed).days <= EVENT_WINDOW_DAYS:
            events.append(event)
    return accounts, events


def parse_owners(data: Any) -> list[Owner]:
    """Current individual persons with significant control (corporate owners are skipped:
    they are not people to talk to)."""
    items = data.get("items") if isinstance(data, dict) else None
    out: list[Owner] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("ceased_on"):
            continue
        if not str(item.get("kind", "")).startswith("individual-person"):
            continue
        parts = item.get("name_elements") or {}
        name = (
            " ".join(
                str(p)
                for p in (parts.get("forename"), parts.get("middle_name"), parts.get("surname"))
                if p
            )
            or str(item.get("name") or "").strip()
        )
        if name:
            natures = tuple(str(n) for n in item.get("natures_of_control") or [])
            out.append(Owner(name, natures, _date(item.get("notified_on"))))
    return out[:MAX_OFFICERS]


def parse_search(data: Any) -> list[RegistryCompany]:
    items = data.get("items") if isinstance(data, dict) else None
    out: list[RegistryCompany] = []
    for item in items if isinstance(items, list) else []:
        if (
            not isinstance(item, dict)
            or not item.get("company_number")
            or not item.get("company_name")
        ):
            continue
        office = item.get("registered_office_address") or {}
        out.append(
            RegistryCompany(
                number=str(item["company_number"]),
                name=" ".join(str(item["company_name"]).split()),
                status=str(item.get("company_status") or "unknown"),
                incorporated=_date(item.get("date_of_creation")),
                locality=office.get("locality"),
                postal_code=office.get("postal_code"),
                sic_codes=tuple(str(c) for c in item.get("sic_codes") or []),
            )
        )
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

    async def filings(
        self, fetcher: SafeHttpFetcher, number: str, today: date
    ) -> tuple[AccountsInfo | None, list[FilingEvent]]:
        data = await self._get(fetcher, f"/company/{number}/filing-history?items_per_page=100")
        return parse_filings(data, today)

    async def owners(self, fetcher: SafeHttpFetcher, number: str) -> list[Owner]:
        try:
            data = await self._get(fetcher, f"/company/{number}/persons-with-significant-control")
        except ProviderError as exc:
            if exc.code == "registry_not_found":  # no PSC register filed: no owners to report
                return []
            raise
        return parse_owners(data)

    async def advanced_search(
        self,
        fetcher: SafeHttpFetcher,
        *,
        sic_codes: list[str],
        location: str | None,
        incorporated_from: date | None,
        incorporated_to: date | None,
        size: int,
    ) -> list[RegistryCompany]:
        params = {"company_status": "active", "sic_codes": ",".join(sic_codes), "size": str(size)}
        if location:
            params["location"] = location
        if incorporated_from:
            params["incorporated_from"] = incorporated_from.isoformat()
        if incorporated_to:
            params["incorporated_to"] = incorporated_to.isoformat()
        return parse_search(
            await self._get(fetcher, f"/advanced-search/companies?{urlencode(params)}")
        )

    async def officers(self, fetcher: SafeHttpFetcher, number: str) -> list[Officer]:
        return parse_officers(
            await self._get(fetcher, f"/company/{number}/officers?items_per_page=35")
        )
