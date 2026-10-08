"""Registry enrichment: the company number on the site, Companies House and Wikidata parsing,
the name check, and how registry facts feed people, ICP and the brief."""

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from app.briefs.grounding import validate
from app.briefs.template import BriefInputs, build, evidence_index, vocabulary
from app.catalogue.defaults import solved_by
from app.catalogue.matching import match_services
from app.intelligence.extractors.registration import extract as registration
from app.intelligence.facts import Fact, Facts, facts_from_observations
from app.intelligence.people import named_people, same_person
from app.intelligence.runner import analyse
from app.intelligence.types import Page, SiteContext
from app.opportunities.detectors import detect
from app.providers.errors import ProviderError
from app.providers.fetch.types import FetchResult
from app.qualification.config import IcpConfigModel
from app.registry import companies_house as ch
from app.registry import wikidata as wd
from app.registry.stage import Registries, collect, name_matches
from app.scoring.config import ScoringConfigModel
from app.scoring.dimensions import buyer_confidence
from app.scoring.engine import assess
from tests.fixtures.sites import IMMIGRATION
from tests.unit.test_brief import CATALOGUE

CTX = SiteContext("https://harbour.test/", "missing")


@pytest.mark.parametrize(
    ("text", "number", "where"),
    [
        ("Harbour Immigration Ltd. Company number 6812345.", "06812345", None),
        ("Registered in England and Wales No. 06812345", "06812345", "England And Wales"),
        ("Registered in Scotland, company no SC123456", "SC123456", "Scotland"),
        ("Reg. No: OC301234 | VAT 123", "OC301234", None),
        ("Registered in England & Wales with number 12345678.", "12345678", "England & Wales"),
    ],
)
def test_the_registered_number_is_read_from_the_site(
    text: str, number: str, where: str | None
) -> None:
    (found,) = registration([Page("https://harbour.test/", f"<p>{text}</p>", "home")], CTX)
    assert found.value == {"number": number, "jurisdiction": where}
    assert found.key == "company.registration_number"


def test_phone_numbers_and_prices_are_not_company_numbers() -> None:
    page = Page("https://x.test/", "<p>Call 020 7946 0001. Plans from 1234567 credits.</p>", "home")
    assert registration([page], CTX) == []


COMPANY = {
    "company_number": "06812345",
    "company_name": "HARBOUR IMMIGRATION LTD",
    "company_status": "active",
    "date_of_creation": "2009-03-02",
    "type": "ltd",
    "sic_codes": ["69109"],
    "registered_office_address": {"locality": "London", "postal_code": "EC2V 6AA"},
}
OFFICERS = {
    "items": [
        {"name": "HART, Amelia Jane", "officer_role": "director", "appointed_on": "2009-03-02"},
        {"name": "OKAFOR, Daniel", "officer_role": "secretary"},
        {"name": "OLD, Former", "officer_role": "director", "resigned_on": "2015-01-01"},
    ]
}


def test_companies_house_records_and_officers_parse() -> None:
    record = ch.parse_company(COMPANY)
    assert record.active and record.incorporated and record.incorporated.year == 2009
    assert record.sic_codes == ["69109"] and record.locality == "London"
    assert not ch.parse_company({**COMPANY, "company_status": "dissolved"}).active
    officers = ch.parse_officers(OFFICERS)
    assert [(o.name, o.role) for o in officers] == [("Amelia Jane Hart", "Director")]
    with pytest.raises(ProviderError):
        ch.parse_company({"company_name": "x"})


def test_wikidata_needs_exactly_one_item_for_the_website() -> None:
    row = {
        "item": {"value": "http://www.wikidata.org/entity/Q42"},
        "itemLabel": {"value": "Harbour Immigration"},
        "inception": {"value": "2009-03-02T00:00:00Z"},
        "employees": {"value": "12"},
        "countryLabel": {"value": "United Kingdom"},
        "chn": {"value": "06812345"},
    }
    record = wd.parse({"results": {"bindings": [row]}})
    assert record is not None and record.qid == "Q42" and record.employees == 12
    assert record.companies_house_number == "06812345"
    other = {**row, "item": {"value": "http://www.wikidata.org/entity/Q43"}}
    assert wd.parse({"results": {"bindings": [row, other]}}) is None
    assert wd.parse({"results": {"bindings": []}}) is None
    query = wd.query_for("harbour.test")
    assert "<https://www.harbour.test/>" in query and "<http://harbour.test>" in query


@pytest.mark.parametrize(
    ("registered", "site", "domain", "ok"),
    [
        ("HARBOUR IMMIGRATION LTD", ["Harbour Immigration"], "harbour.test", True),
        ("HARBOUR ADVISERS LIMITED", [], "harbourimmigration.co.uk", True),  # domain word
        ("ACME WIDGETS LTD", ["Harbour Immigration"], "harbour.test", False),
        ("THE SERVICES GROUP LTD", ["Group Services"], "x.test", False),  # generic words only
    ],
)
def test_registered_name_must_match_the_site(
    registered: str, site: list[str], domain: str, ok: bool
) -> None:
    assert name_matches(registered, site, domain) is ok


class FakeFetcher:
    """Answers registry API calls; records them for assertions."""

    def __init__(self, company: dict[str, Any] | None, wiki_rows: list[dict[str, Any]]) -> None:
        self.company = company
        self.wiki_rows = wiki_rows
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def fetch(
        self, url: str, *, headers: dict[str, str] | None = None, content_types: Any = None
    ) -> FetchResult:
        self.calls.append((url, headers or {}))
        if "sparql" in url:
            assert "harbour.test" in parse_qs(urlsplit(url).query)["query"][0]
            body = {"results": {"bindings": self.wiki_rows}}
        elif url.endswith("/officers?items_per_page=35"):
            body = OFFICERS
        elif self.company is None:
            return FetchResult(url, url, 404, {}, "application/json", b"{}")
        else:
            body = self.company
        return FetchResult(url, url, 200, {}, "application/json", json.dumps(body).encode())


def _facts(number: str | None = "06812345") -> Facts:
    items = [Fact("company.name", "Harbour Immigration Ltd", 0.85, "e1", "https://harbour.test/")]
    if number:
        items.append(
            Fact(
                "company.registration_number",
                {"number": number},
                0.9,
                "e2",
                "https://harbour.test/",
            )
        )
    return Facts(items)


async def test_collect_looks_up_the_number_and_its_officers() -> None:
    fetcher = FakeFetcher(COMPANY, [])
    found, report = await collect(
        _facts(),
        "harbour.test",
        fetcher,
        Registries(ch.CompaniesHouse("key"), wd.Wikidata()),  # type: ignore[arg-type]
    )
    assert [o.key for o in found] == ["registry.companies_house", "registry.officer"]
    assert (
        report["companies_house"] == "06812345 (active)"
        and report["wikidata"] == "no item for this website"
    )
    assert found[0].source_url.endswith("/company/06812345")
    assert "Companies House 06812345: HARBOUR IMMIGRATION LTD, active" in found[0].excerpt
    auth = next(h for u, h in fetcher.calls if "/company/06812345" in u)["Authorization"]
    assert auth.startswith("Basic ")  # key sent as Basic auth, never in the URL
    assert all("key" not in u for u, _ in fetcher.calls)


async def test_collect_degrades_without_a_key_on_mismatch_and_when_missing() -> None:
    no_key = Registries(ch.CompaniesHouse(None), wd.Wikidata(enabled=False))
    found, report = await collect(_facts(), "harbour.test", FakeFetcher(COMPANY, []), no_key)  # type: ignore[arg-type]
    assert found == [] and report["companies_house"] == "skipped: no API key (number 06812345)"

    keyed = Registries(ch.CompaniesHouse("key"), wd.Wikidata(enabled=False))
    other = {**COMPANY, "company_name": "ACME WIDGETS LTD"}
    found, report = await collect(_facts(), "harbour.test", FakeFetcher(other, []), keyed)  # type: ignore[arg-type]
    assert found == [] and report["companies_house"] == "name mismatch"

    found, report = await collect(_facts(), "harbour.test", FakeFetcher(None, []), keyed)  # type: ignore[arg-type]
    assert found == [] and "Not on the Companies House register" in report["errors"][0]


async def test_wikidata_can_supply_the_number_when_the_site_does_not() -> None:
    row = {
        "item": {"value": "http://www.wikidata.org/entity/Q42"},
        "itemLabel": {"value": "Harbour Immigration"},
        "chn": {"value": "06812345"},
    }
    regs = Registries(ch.CompaniesHouse("key"), wd.Wikidata())
    found, report = await collect(_facts(None), "harbour.test", FakeFetcher(COMPANY, [row]), regs)  # type: ignore[arg-type]
    assert [o.key for o in found] == [
        "registry.wikidata",
        "registry.companies_house",
        "registry.officer",
    ]
    assert report["wikidata"] == "Q42"


def _registry_facts(status: str = "active") -> list[Any]:
    from app.registry.stage import company_observation, officer_observation

    return [
        company_observation(ch.parse_company({**COMPANY, "company_status": status})),
        officer_observation("06812345", "Amelia Jane Hart", "Director", "2009-03-02"),
        officer_observation("06812345", "Priya Shah", "Director", None),
    ]


def test_officers_join_site_people_without_double_counting() -> None:
    facts = facts_from_observations([*analyse(*IMMIGRATION)[0], *_registry_facts()])
    names = [p.value["name"] for p in named_people(facts)]
    assert names == ["Amelia Hart", "Daniel Okafor", "Priya Shah"]  # Amelia Jane Hart = Amelia Hart
    assert same_person("Amelia Hart", "amelia jane hart") and not same_person("A Hart", "B Hart")
    assert buyer_confidence(facts).score == 95  # two named deciders + a published contact route


def _assess(facts: Facts):  # type: ignore[no-untyped-def]
    candidates = detect(facts)
    return candidates, assess(
        facts,
        candidates,
        solved_by=solved_by(),
        icp_config=IcpConfigModel(),
        scoring_config=ScoringConfigModel(),
    )


def test_a_dissolved_company_is_rejected_as_inactive() -> None:
    facts = facts_from_observations([*analyse(*IMMIGRATION)[0], *_registry_facts("dissolved")])
    _, a = _assess(facts)
    assert a.icp.hard_reject and a.icp.rejection_reason == "inactive_company"
    assert any("Companies House status: dissolved" in h.note for h in a.icp.hits)


def test_the_registry_claim_in_the_brief_is_grounded() -> None:
    facts = facts_from_observations([*analyse(*IMMIGRATION)[0], *_registry_facts()])
    candidates, a = _assess(facts)
    inputs = BriefInputs(facts, candidates, match_services(candidates, CATALOGUE), None, a, [])
    draft = build(inputs)
    texts = [c.text for c in draft.sections["company_overview"].claims]
    assert (
        "Registered with Companies House as HARBOUR IMMIGRATION LTD (06812345), status active, "
        "incorporated 2009-03-02." in texts
    )
    _, dropped = validate(draft.claims(), evidence_index(facts), vocabulary(inputs))
    assert dropped == []
