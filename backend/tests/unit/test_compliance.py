"""Website compliance and health (slice 8.2): what a site must show by law or its regulator,
the Wayback Machine and Safe Browsing checks, and the opportunity they raise."""

import asyncio
import json
from datetime import date

import httpx
import pytest

from app.intelligence.extractors import compliance
from app.intelligence.facts import facts_from_observations
from app.intelligence.types import Observation, Page, SiteContext
from app.opportunities.detectors import website_compliance, website_rebuild
from app.providers.errors import ProviderError, ProviderUnavailable
from app.sitecheck import safebrowsing, wayback
from app.sitecheck.stage import SiteChecks, collect

BADGE = (
    '<div><iframe frameborder="0" scrolling="no" src="https://cdn.yoshki.com/iframe/55845r.html">'
    "</iframe></div>"
)


def page(
    body: str, url: str = "https://firm.test/", category: str = "home", head: str = ""
) -> Page:
    return Page(url, f"<html><head>{head}</head><body>{body}</body></html>", category)


def found(*pages: Page) -> dict[str, Observation]:
    out = compliance.extract(list(pages), SiteContext(pages[0].url, "parsed"))
    assert len({o.key for o in out}) == len(out)
    return {o.key: o for o in out}


COMPLIANT_FOOTER = (
    "<footer>Bright Legal Ltd, registered in England and Wales, company number 01234567. "
    "Authorised and regulated by the Solicitors Regulation Authority, SRA number 612345. "
    f"{BADGE}</footer>"
)


def test_a_compliant_law_firm_shows_everything_the_sra_asks() -> None:
    home = page(f"<h1>Immigration solicitors</h1><p>Visa applications.</p>{COMPLIANT_FOOTER}")
    fees = page(
        "<h1>Our fees</h1><p>Spouse visa application: fixed fee £1,450 plus VAT.</p>",
        "https://firm.test/fees",
        "pricing",
    )
    complaints = page(
        "<h1>Complaints</h1><p>If you are unhappy you may complain to the Legal Ombudsman.</p>",
        "https://firm.test/complaints",
        "about",
    )
    got = found(home, fees, complaints)
    assert got["compliance.sra_regulated"].value is True
    assert got["compliance.sra_badge"].value is True
    assert "yoshki" in got["compliance.sra_badge"].excerpt
    assert got["compliance.sra_number"].value == {"number": "612345"}
    assert got["compliance.complaints_procedure"].value is True
    assert got["compliance.complaints_procedure"].source_url == "https://firm.test/complaints"
    assert got["compliance.price_information"].value == {
        "service": "immigration",
        "published": True,
    }
    assert got["compliance.price_information"].source_url == "https://firm.test/fees"
    assert got["compliance.company_number_shown"].value is True
    candidate = website_compliance(facts_from_observations(got.values()))
    assert candidate is None


def test_a_law_firm_missing_the_sra_items_is_reported_page_by_page() -> None:
    home = page(
        "<h1>Immigration law</h1><p>Visa help. Regulated by the Solicitors Regulation Authority."
        "</p><footer>Bright Legal Ltd</footer>"
    )
    about = page("<h1>About</h1><p>Since 2009.</p>", "https://firm.test/about", "about")
    got = found(home, about)
    for key in (
        "compliance.sra_badge",
        "compliance.sra_number",
        "compliance.complaints_procedure",
        "compliance.company_number_shown",
    ):
        assert got[key].value is False, key
        assert "Not found on the 2 pages crawled" in got[key].excerpt
    assert got["compliance.price_information"].value == {
        "service": "immigration",
        "published": False,
    }
    candidate = website_compliance(facts_from_observations(got.values()))
    assert candidate is not None
    assert candidate.title == "Website compliance fixes"
    assert candidate.rule_key == "website_rebuild.compliance_gaps"
    assert "no SRA digital badge" in candidate.problem
    assert "no published prices for immigration work" in candidate.problem
    assert candidate.confidence == 0.85


def test_sites_that_are_not_law_firms_get_no_sra_rules() -> None:
    got = found(page("<h1>Accountants</h1><p>Tax returns for small firms.</p>"))
    assert not any(k.startswith("compliance.sra") for k in got)
    assert "compliance.price_information" not in got


def test_the_badge_alone_or_calling_itself_solicitors_brings_in_the_sra_rules() -> None:
    badge_only = found(page(f"<h1>Immigration law</h1><footer>{BADGE}</footer>"))
    assert badge_only["compliance.sra_regulated"].excerpt.startswith("Shows the SRA badge")
    assert badge_only["compliance.sra_badge"].value is True

    # A firm of solicitors that shows nothing of the SRA: the biggest gap, not a skip.
    silent = found(
        page(
            "<h1>Hart Solicitors</h1><p>Family and immigration matters.</p>",
            head="<title>Hart Solicitors | London</title>",
        )
    )
    regulated = silent["compliance.sra_regulated"]
    assert regulated.excerpt.startswith("Describes itself as solicitors")
    assert regulated.confidence == 0.75
    assert silent["compliance.sra_badge"].value is False
    assert silent["compliance.sra_number"].value is False

    number_only = found(page("<h1>Firm</h1><footer>SRA No: 8014841</footer>"))
    assert number_only["compliance.sra_number"].value == {"number": "8014841"}


def test_a_web_agency_named_in_a_credit_is_not_the_business() -> None:
    credit = found(page("<h1>Hart Law</h1><footer>Website by Webist Ltd</footer>"))
    assert "compliance.company_number_shown" not in credit
    for footer in ("Designed and developed by Pixel Works Limited", "Powered by: Sitey LLP"):
        assert "compliance.company_number_shown" not in found(page(f"<footer>{footer}</footer>"))
    own = found(page("<footer>© 2024 Hart Law Ltd. Website by Webist Ltd</footer>"))
    assert own["compliance.company_number_shown"].value is False
    assert '"Hart Law Ltd"' in own["compliance.company_number_shown"].excerpt


def test_a_fees_page_for_other_work_does_not_count_as_immigration_prices() -> None:
    home = page("<h1>CJ Solicitors</h1><p>Immigration and visa advice. Regulated by the SRA.</p>")
    fees = page(
        "<h1>Pricing and fees</h1><p>Debt recovery: fixed fee £750.</p>",
        "https://firm.test/pricing-fees",
        "pricing",
    )
    prices = found(home, fees)["compliance.price_information"]
    assert prices.value == {"service": "immigration", "published": False}
    assert prices.source_url == "https://firm.test/pricing-fees"
    assert "gives prices but not for immigration work" in prices.excerpt

    # A menu naming "Immigration" far from the amounts does not count either.
    menu = "<nav>Home Immigration Family Debt</nav>"
    filler = "Our team is experienced and friendly. " * 10
    with_menu = page(
        f"{menu}<h1>Pricing and fees</h1><p>{filler}</p><p>Debt recovery: fixed fee £750.</p>",
        "https://firm.test/pricing-fees",
        "pricing",
    )
    assert found(home, with_menu)["compliance.price_information"].value["published"] is False


def test_trackers_without_a_consent_tool_are_found_and_a_tool_is_named() -> None:
    gtag = '<script src="https://www.googletagmanager.com/gtag/js?id=G-1"></script>'
    pixel = '<script>!function(){};n.src="https://connect.facebook.net/en_US/fbevents.js"</script>'
    bare = found(page("<h1>Shop</h1>", head=gtag + pixel))
    assert bare["compliance.cookie_consent"].value == {
        "trackers": ["Google Analytics", "Meta Pixel"],
        "consent_tool": None,
    }
    tool = '<script src="https://consent.cookiebot.com/uc.js"></script>'
    with_tool = found(page("<h1>Shop</h1>", head=gtag + tool))
    assert with_tool["compliance.cookie_consent"].value["consent_tool"] == "Cookiebot"
    assert "compliance.cookie_consent" not in found(page("<h1>No trackers</h1>"))


def test_one_weak_gap_alone_raises_nothing_but_two_do() -> None:
    gtag = '<script src="https://www.googletagmanager.com/gtag/js?id=G-1"></script>'
    one = found(page("<h1>Shop</h1>", head=gtag))
    assert website_compliance(facts_from_observations(one.values())) is None
    two = found(page("<h1>Shop</h1><footer>Acme Widgets Ltd</footer>", head=gtag))
    candidate = website_compliance(facts_from_observations(two.values()))
    assert candidate is not None and candidate.confidence == 0.69
    assert set(candidate.signals) == {
        "compliance.company_number_shown",
        "compliance.cookie_consent",
    }


def obs(key: str, value: object) -> Observation:
    from app.core.enums import ObservationArea

    return Observation(ObservationArea.WEBSITE, key, value, "https://firm.test/", "x")


def test_a_safe_browsing_listing_alone_raises_compliance_and_old_archives_count_as_neglect() -> (
    None
):
    flagged = facts_from_observations([obs("website.safe_browsing", {"threats": ["MALWARE"]})])
    candidate = website_compliance(flagged)
    assert candidate is not None and "warns visitors away" in candidate.problem
    assert (
        website_compliance(facts_from_observations([obs("website.safe_browsing", {"threats": []})]))
        is None
    )

    old = facts_from_observations(
        [
            obs("website.archive", {"years_unchanged": 5.2, "last_changed": "2021-08-01"}),
            obs("website.https", False),
        ]
    )
    rebuild = website_rebuild(old)
    assert rebuild is not None
    assert "has not changed in 5.2 years (Wayback Machine)" in rebuild.problem
    recent = facts_from_observations(
        [obs("website.archive", {"years_unchanged": 0.4}), obs("website.https", False)]
    )
    assert website_rebuild(recent) is None


def cdx(*rows: list[str]) -> bytes:
    return json.dumps([["timestamp", "digest"], *rows]).encode()


def test_wayback_reports_first_capture_and_last_change() -> None:
    record = wayback.parse(
        cdx(["20060701120000"]), cdx(["20190101000000", "A"], ["20210815093000", "B"])
    )
    assert record == wayback.ArchiveRecord(date(2006, 7, 1), date(2021, 8, 15), 2)
    assert wayback.parse(b"", b"") is None
    assert wayback.parse(b"[]", b"[]") is None
    with pytest.raises(ProviderError):
        wayback.parse(b"not json", b"[]")


def test_safe_browsing_reads_threats_and_a_refused_key_is_unavailable() -> None:
    assert safebrowsing.parse({}) == []
    assert safebrowsing.parse(
        {"matches": [{"threatType": "MALWARE"}, {"threatType": "SOCIAL_ENGINEERING"}]}
    ) == ["MALWARE", "SOCIAL_ENGINEERING"]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "k"
        assert json.loads(request.content)["threatInfo"]["threatEntries"] == [
            {"url": "https://firm.test/"}
        ]
        return httpx.Response(200, json={"matches": [{"threatType": "MALWARE"}]})

    client = safebrowsing.SafeBrowsing("k", transport=httpx.MockTransport(handler))
    assert asyncio.run(client.threats("https://firm.test/")) == ["MALWARE"]
    refused = safebrowsing.SafeBrowsing(
        "bad", transport=httpx.MockTransport(lambda _r: httpx.Response(403))
    )
    with pytest.raises(ProviderUnavailable):
        asyncio.run(refused.threats("https://firm.test/"))


class FakeWayback(wayback.Wayback):
    def __init__(self, record: wayback.ArchiveRecord | None, fail: bool = False) -> None:
        super().__init__(enabled=True)
        self.record, self.fail = record, fail

    async def lookup(self, fetcher, domain):  # type: ignore[no-untyped-def]
        if self.fail:
            raise ProviderError("Timed out", code="timeout")
        return self.record


def test_site_checks_record_what_they_found_and_report_what_they_could_not() -> None:
    record = wayback.ArchiveRecord(date(2006, 7, 1), date(2021, 8, 15), 12)
    checks = SiteChecks(FakeWayback(record), safebrowsing.SafeBrowsing(None))
    found_, report = asyncio.run(
        collect("firm.test", "https://firm.test/", None, checks, date(2026, 8, 15))  # type: ignore[arg-type]
    )
    [archive] = found_
    assert archive.key == "website.archive"
    assert archive.value == {
        "first_captured": "2006-07-01",
        "last_changed": "2021-08-15",
        "years_unchanged": 5.0,
        "recent_versions": 12,
    }
    assert archive.source_url == "https://web.archive.org/web/*/firm.test"
    assert report == {
        "website_archive": "last changed 2021-08-15",
        "safe_browsing": "not configured",
    }

    failing = SiteChecks(FakeWayback(None, fail=True), safebrowsing.SafeBrowsing(None))
    nothing, report = asyncio.run(
        collect("firm.test", "https://firm.test/", None, failing, date(2026, 8, 15))  # type: ignore[arg-type]
    )
    assert nothing == []
    assert report["website_archive"] == "failed"
    assert report["site_check_errors"] == ["wayback: Timed out"]

    off = SiteChecks.disabled()
    assert asyncio.run(
        collect("firm.test", "https://firm.test/", None, off, date(2026, 8, 15))  # type: ignore[arg-type]
    ) == ([], {"website_archive": "disabled", "safe_browsing": "not configured"})
