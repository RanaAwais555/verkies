"""The Solicitors Regulation Authority's register, through its Data Share API (slice 8.1).

One call returns every organisation the SRA has records for (about 25,000, 25MB), refreshed by
the SRA every 24 hours. A free subscription key from the SRA's developer portal goes in the
Ocp-Apim-Subscription-Key header. The terms ask for the key to stay confidential and for the
attribution statement below wherever the data is shown.
"""

import json
from datetime import date
from typing import Any

from app.config import Settings
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.registers.sources import RegisterEntry, company_number, postcode_area, text, website

API = "https://sra-prod-apim.azure-api.net/datashare/api/V1/organisation/GetAll"
# Authorised now (YES), or authorised with conditions on its practice.
ACTIVE_STATUSES = frozenset({"YES", "CONDITION"})
JSON_TYPES = frozenset({"application/json", "text/json"})


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _head_office(offices: list[dict[str, Any]]) -> dict[str, Any]:
    return next((o for o in offices if o.get("OfficeType") == "HO"), offices[0] if offices else {})


def parse_organisation(org: Any) -> RegisterEntry | None:
    if not isinstance(org, dict) or not org.get("SraNumber") or not org.get("PracticeName"):
        return None
    offices = [o for o in org.get("Offices") or [] if isinstance(o, dict)]
    head = _head_office(offices)
    sites = [str(s) for s in org.get("Websites") or [] if s] + [
        str(o["Website"]) for o in offices if o.get("Website")
    ]
    status = org.get("AuthorisationStatus")
    return RegisterEntry(
        source_id=str(org["SraNumber"]),
        name=text(org["PracticeName"], 300) or str(org["SraNumber"]),
        active=status in ACTIVE_STATUSES,
        status=text(status or org.get("Type"), 80),
        legal_form=text(org.get("Constitution"), 80),
        company_number=company_number(org.get("CompanyRegNo")),
        website=next((w for w in map(website, sites) if w), None),
        phone=text(head.get("PhoneNumber"), 40),
        email=text(head.get("Email"), 320),
        postcode=text(head.get("Postcode"), 12),
        town=text(head.get("Town"), 120),
        postcode_areas=tuple(
            sorted({a for a in (postcode_area(o.get("Postcode")) for o in offices) if a})
        ),
        areas=tuple(str(a)[:120] for a in org.get("WorkArea") or [] if a),
        office_count=org.get("NoOfOffices") if isinstance(org.get("NoOfOffices"), int) else None,
        authorised_on=_date(org.get("AuthorisationDate")),
        data={
            "type": org.get("Type"),
            "trading_names": org.get("TradingNames") or [],
            "offices": [
                {"postcode": o.get("Postcode"), "town": o.get("Town"), "type": o.get("OfficeType")}
                for o in offices[:20]
            ],
        },
    )


def parse(body: bytes) -> list[RegisterEntry]:
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise ProviderError("The SRA returned invalid JSON.", code="register_bad_output") from exc
    orgs = payload.get("Organisations") if isinstance(payload, dict) else None
    if not isinstance(orgs, list):
        raise ProviderError("The SRA returned no organisations.", code="register_bad_output")
    entries: dict[str, RegisterEntry] = {}
    for entry in map(parse_organisation, orgs):
        if entry:
            entries.setdefault(entry.source_id, entry)  # listed twice: keep the first
    return list(entries.values())


class SraRegister:
    key = "sra"
    short_name = "SRA"
    name = "Solicitors Regulation Authority"
    publisher = "Solicitors Regulation Authority"
    attribution = (
        "Contains data from the Solicitors Regulation Authority's register of regulated "
        "firms, reused under the SRA's data sharing terms."
    )
    cadence_hours = 24
    area_label = "Area of work"
    has_location = True
    has_income = False
    has_offices = True
    specialist_areas: int | None = 3

    def __init__(self, url: str = API) -> None:
        self.url = url

    def configured(self, settings: Settings) -> bool:
        key = settings.sra_api_key
        return bool(key and key.get_secret_value())

    async def download(self, fetcher: SafeHttpFetcher, settings: Settings) -> dict[str, bytes]:
        key = settings.sra_api_key
        if not key or not key.get_secret_value():
            raise ProviderUnavailable("The SRA register needs VROS_SRA_API_KEY.")
        result = await fetcher.fetch(
            self.url,
            headers={"Ocp-Apim-Subscription-Key": key.get_secret_value()},
            content_types=JSON_TYPES,
        )
        if result.status in (401, 403):
            raise ProviderUnavailable("The SRA refused the subscription key.")
        if result.status != 200:
            raise ProviderError(f"The SRA returned {result.status}.", code="register_error")
        return {"organisations": result.body}

    def parse(self, files: dict[str, bytes]) -> list[RegisterEntry]:
        return parse(files["organisations"])
