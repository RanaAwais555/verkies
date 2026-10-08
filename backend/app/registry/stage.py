"""Enrich stage: official registry facts for the researched company (master context §15,
PROVIDER_SPEC.md §3). Runs after signals.

- Wikidata: the item whose official website is this domain (exactly one, or nothing).
- Companies House: by the registered number printed on the company's own site (or recorded in
  that Wikidata item). The record is accepted only if its name shares a distinctive word with
  the company's name on the site or its domain, so a mistyped number cannot attach another
  company. Current directors and LLP members are kept as named officers.

Every fact is an observation in the `registry` area whose evidence cites the public registry
page. A registry that is unconfigured, down or has no match is reported, never fatal.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.core.enums import EvidenceType, ObservationArea
from app.intelligence.facts import Facts
from app.intelligence.stage import persist_observation
from app.intelligence.types import Observation
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.registry.companies_house import (
    PUBLIC_PAGE,
    AccountsInfo,
    CompaniesHouse,
    CompanyRecord,
    FilingEvent,
    Owner,
)
from app.registry.wikidata import Wikidata, WikidataRecord
from app.research.models import ResearchRun
from app.scoring.stage import load_facts

GENERIC = frozenset(
    {"ltd", "limited", "plc", "llp", "lp", "the", "and", "of", "co", "company", "group", "uk"}
    | {"holdings", "services", "international"}
)


@dataclass(frozen=True)
class Registries:
    companies_house: CompaniesHouse
    wikidata: Wikidata

    @classmethod
    def from_settings(cls, settings: Settings) -> "Registries":
        key = settings.companies_house_api_key
        return cls(
            CompaniesHouse(key.get_secret_value() if key else None),
            Wikidata(enabled=settings.wikidata_enabled),
        )

    @classmethod
    def disabled(cls) -> "Registries":
        return cls(CompaniesHouse(None), Wikidata(enabled=False))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in GENERIC}


def name_matches(registered: str, site_names: list[str], domain: str) -> bool:
    """True when the registered name shares a distinctive word with what the site calls
    itself or with its domain name."""
    words = _words(registered)
    label = domain.split(".")[0].lower()
    if any(w in label for w in words if len(w) >= 4):
        return True
    return any(words & _words(name) for name in site_names)


def wikidata_observation(record: WikidataRecord) -> Observation:
    details = [
        f"inception {record.inception.isoformat()}" if record.inception else None,
        f"{record.employees} employees" if record.employees is not None else None,
        record.country,
        ", ".join(record.industries) or None,
    ]
    return Observation(
        ObservationArea.REGISTRY,
        "registry.wikidata",
        {
            "qid": record.qid,
            "label": record.label,
            "inception": record.inception.isoformat() if record.inception else None,
            "employees": record.employees,
            "country": record.country,
            "industries": list(record.industries),
        },
        record.url,
        f"Wikidata {record.qid}: {record.label}" + "".join(f"; {d}" for d in details if d),
        evidence_type=EvidenceType.COMPANY_REGISTRY,
        confidence=0.8,
    )


def company_observation(record: CompanyRecord) -> Observation:
    when = record.incorporated.isoformat() if record.incorporated else "unknown date"
    sic = f", SIC {' '.join(record.sic_codes)}" if record.sic_codes else ""
    return Observation(
        ObservationArea.REGISTRY,
        "registry.companies_house",
        {
            "number": record.number,
            "name": record.name,
            "status": record.status,
            "active": record.active,
            "incorporated": record.incorporated.isoformat() if record.incorporated else None,
            "type": record.company_type,
            "sic_codes": record.sic_codes,
            "locality": record.locality,
            "postal_code": record.postal_code,
            "has_insolvency_history": record.has_insolvency_history,
        },
        PUBLIC_PAGE.format(number=record.number),
        f"Companies House {record.number}: {record.name}, {record.status}, "
        f"incorporated {when}{sic}",
        evidence_type=EvidenceType.COMPANY_REGISTRY,
        confidence=0.95,
    )


def officer_observation(number: str, name: str, role: str, appointed: str | None) -> Observation:
    since = f", appointed {appointed}" if appointed else ""
    return Observation(
        ObservationArea.REGISTRY,
        "registry.officer",
        {"name": name, "role": role, "appointed": appointed, "number": number},
        PUBLIC_PAGE.format(number=number) + "/officers",
        f"Companies House {number} officer: {name}, {role}{since}",
        evidence_type=EvidenceType.COMPANY_REGISTRY,
        confidence=0.95,
    )


async def collect(
    facts: Facts,
    domain: str,
    fetcher: SafeHttpFetcher,
    registries: Registries,
    today: date | None = None,
) -> tuple[list[Observation], dict[str, Any]]:
    found: list[Observation] = []
    report: dict[str, Any] = {"wikidata": "disabled", "companies_house": "no number", "errors": []}

    wiki: WikidataRecord | None = None
    if registries.wikidata.enabled:
        try:
            wiki = await registries.wikidata.lookup(fetcher, domain)
            report["wikidata"] = wiki.qid if wiki else "no item for this website"
        except ProviderError as exc:
            report["wikidata"] = "failed"
            report["errors"].append(f"wikidata: {exc.message}")
    if wiki:
        found.append(wikidata_observation(wiki))

    on_site = facts.value("company.registration_number") or {}
    number = on_site.get("number") or (wiki.companies_house_number if wiki else None)
    if not number:
        return found, report
    if not registries.companies_house.configured:
        report["companies_house"] = f"skipped: no API key (number {number})"
        return found, report
    try:
        record = await registries.companies_house.company(fetcher, number)
    except ProviderUnavailable as exc:
        report["companies_house"] = "unavailable"
        report["errors"].append(f"companies house: {exc.message}")
        return found, report
    except ProviderError as exc:
        report["companies_house"] = "failed"
        report["errors"].append(f"companies house {number}: {exc.message}")
        return found, report
    site_names = [str(f.value) for f in facts.all("company.name")] + ([wiki.label] if wiki else [])
    if not name_matches(record.name, site_names, domain):
        report["companies_house"] = "name mismatch"
        report["errors"].append(
            f"companies house {number}: registered name {record.name!r} does not match the site"
        )
        return found, report
    found.append(company_observation(record))
    report["companies_house"] = f"{record.number} ({record.status})"
    try:
        officers = await registries.companies_house.officers(fetcher, record.number)
    except ProviderError as exc:
        report["errors"].append(f"companies house officers: {exc.message}")
        officers = []
    for officer in officers:
        found.append(
            officer_observation(
                record.number,
                officer.name,
                officer.role,
                officer.appointed.isoformat() if officer.appointed else None,
            )
        )
    report["officers"] = len(officers)
    found += await _depth(registries.companies_house, fetcher, record.number, today, report)
    return found, report


async def _depth(
    client: CompaniesHouse,
    fetcher: SafeHttpFetcher,
    number: str,
    today: date | None,
    report: dict[str, Any],
) -> list[Observation]:
    """Filed accounts (size), dated filings that signal change, and the people with
    significant control. Each part degrades on its own."""
    found: list[Observation] = []
    today = today or datetime.now(UTC).date()
    try:
        accounts, events = await client.filings(fetcher, number, today)
    except ProviderError as exc:
        report["errors"].append(f"companies house filings: {exc.message}")
        accounts, events = None, []
    if accounts:
        found.append(accounts_observation(number, accounts))
    found += [filing_observation(number, e) for e in events]
    report["filing_events"] = len(events)
    try:
        owners = await client.owners(fetcher, number)
    except ProviderError as exc:
        report["errors"].append(f"companies house owners: {exc.message}")
        owners = []
    found += [owner_observation(number, o) for o in owners]
    report["owners"] = len(owners)
    return found


def accounts_observation(number: str, accounts: AccountsInfo) -> Observation:
    made_up = f", made up to {accounts.made_up_to.isoformat()}" if accounts.made_up_to else ""
    return Observation(
        ObservationArea.REGISTRY,
        "registry.accounts",
        {
            "type": accounts.accounts_type,
            "size_band": accounts.size_band,
            "made_up_to": accounts.made_up_to.isoformat() if accounts.made_up_to else None,
            "filed": accounts.filed.isoformat() if accounts.filed else None,
        },
        PUBLIC_PAGE.format(number=number) + "/filing-history",
        f"Companies House {number} accounts: {accounts.accounts_type.replace('-', ' ')}{made_up}",
        evidence_type=EvidenceType.COMPANY_REGISTRY,
        confidence=0.95,
    )


def filing_observation(number: str, event: FilingEvent) -> Observation:
    return Observation(
        ObservationArea.SIGNALS,
        "signal.filing",
        {"signal": event.signal, "title": event.title, "published": event.filed.isoformat()},
        PUBLIC_PAGE.format(number=number) + "/filing-history",
        f"Companies House {number} filing: {event.title} — filed {event.filed.isoformat()}",
        evidence_type=EvidenceType.COMPANY_REGISTRY,
        confidence=0.9,
        published_at=datetime.combine(event.filed, time(), tzinfo=UTC),
    )


def owner_observation(number: str, owner: Owner) -> Observation:
    control = "; ".join(n.replace("-", " ") for n in owner.natures[:2])
    return Observation(
        ObservationArea.REGISTRY,
        "registry.owner",
        {
            "name": owner.name,
            "natures": list(owner.natures),
            "notified": owner.notified.isoformat() if owner.notified else None,
            "number": number,
        },
        PUBLIC_PAGE.format(number=number) + "/persons-with-significant-control",
        f"Companies House {number} person with significant control: {owner.name}"
        + (f" ({control})" if control else ""),
        evidence_type=EvidenceType.COMPANY_REGISTRY,
        confidence=0.95,
    )


async def enrich_stage(
    run_id: uuid.UUID,
    sessionmaker: async_sessionmaker[AsyncSession],
    fetcher: SafeHttpFetcher,
    registries: Registries,
) -> dict[str, Any]:
    async with sessionmaker() as db:
        run = await db.get(ResearchRun, run_id)
        assert run is not None
        attempt, domain = run.retry_count, run.normalised_domain
        facts = await load_facts(db, run)
    observations, report = await collect(facts, domain, fetcher, registries)
    async with sessionmaker() as db:
        for observation in observations:
            persist_observation(db, run_id, attempt, observation)
        await db.commit()
    return report
