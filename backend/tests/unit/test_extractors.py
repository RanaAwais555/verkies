"""Extractors against fixture sites: exact observations and their evidence."""

from typing import Any

import pytest

from app.core.enums import EvidenceType
from app.intelligence.runner import EXTRACTORS, analyse
from app.intelligence.types import Observation
from tests.fixtures.sites import HOLDING, IMMIGRATION, SAAS


def run(fixture: tuple[Any, Any]) -> dict[str, list[Observation]]:
    observations, failed = analyse(*fixture)
    assert failed == []
    found: dict[str, list[Observation]] = {}
    for o in observations:
        found.setdefault(o.key, []).append(o)
    return found


def one(found: dict[str, list[Observation]], key: str) -> Observation:
    assert key in found, f"{key} missing; have {sorted(found)}"
    assert len(found[key]) == 1, found[key]
    return found[key][0]


def values(found: dict[str, list[Observation]], key: str) -> list[Any]:
    return [o.value for o in found.get(key, [])]


@pytest.fixture(scope="module")
def harbour() -> dict[str, list[Observation]]:
    return run(IMMIGRATION)


@pytest.fixture(scope="module")
def shiplane() -> dict[str, list[Observation]]:
    return run(SAAS)


# --- every observation is backed by evidence ---------------------------------------------


@pytest.mark.parametrize("fixture", [IMMIGRATION, SAAS, HOLDING])
def test_every_observation_has_source_excerpt_and_confidence(fixture: tuple[Any, Any]) -> None:
    observations, _ = analyse(*fixture)
    urls = {p.url for p in fixture[0]}
    for o in observations:
        assert o.source_url in urls, o
        assert o.excerpt.strip(), o
        assert 0 < o.confidence <= 1, o
        assert o.source_url in o.seen_on
        assert len(o.excerpt) <= 320


# --- immigration firm --------------------------------------------------------------------


def test_harbour_website_health(harbour: dict[str, list[Observation]]) -> None:
    assert one(harbour, "website.https").value is True
    hsts = one(harbour, "website.hsts")
    assert hsts.value is False and hsts.evidence_type == EvidenceType.HTTP_HEADER
    assert one(harbour, "website.mobile_viewport").value is False
    assert one(harbour, "website.copyright_year").value == 2017
    assert one(harbour, "website.stale_copyright").value >= 9
    broken = one(harbour, "website.broken_internal_links")
    assert broken.value == ["https://harbourimmigration.co.uk/old-fees/"]
    assert broken.source_url == "https://harbourimmigration.co.uk/"


def test_harbour_technology(harbour: dict[str, list[Observation]]) -> None:
    names = {v["name"] for v in values(harbour, "technology.detected")}
    assert {"WordPress", "jQuery", "PHP", "Apache"} <= names
    wordpress = next(o for o in harbour["technology.detected"] if o.value["name"] == "WordPress")
    assert "WordPress 5.2.4" in wordpress.excerpt  # the generator tag is the strongest marker
    assert wordpress.evidence_type == EvidenceType.TECHNOLOGY_FINGERPRINT
    assert one(harbour, "technology.generator").value == "WordPress 5.2.4"


def test_harbour_conversion(harbour: dict[str, list[Observation]]) -> None:
    form = one(harbour, "conversion.contact_form")
    assert form.value is True and form.source_url.endswith("/contact/")
    assert "your-email" in form.excerpt
    assert one(harbour, "conversion.contact_form_fields").value == [
        "name",
        "email",
        "phone",
        "message",
    ]
    assert one(harbour, "conversion.booking_tool").value is None
    assert one(harbour, "conversion.booking_tool").confidence == 0.6  # absence is weaker evidence
    assert one(harbour, "conversion.live_chat").value is None
    assert one(harbour, "conversion.phone_numbers").value == ["+44 20 7946 0001"]
    assert one(harbour, "conversion.email_addresses").value == ["info@harbourimmigration.co.uk"]
    assert one(harbour, "conversion.testimonials").value is True
    assert set(one(harbour, "conversion.trust_signals").value) >= {"IAA-regulated", "award-winning"}
    assert one(harbour, "conversion.pricing_page").value is False
    assert one(harbour, "conversion.home_ctas").value == ["Contact us"]


def test_harbour_seo(harbour: dict[str, list[Observation]]) -> None:
    title = one(harbour, "seo.home_title").value
    assert title["text"] == "Harbour Immigration | UK Visa Advisers in London"
    assert one(harbour, "seo.home_meta_description").value["length"] > 50
    assert one(harbour, "seo.structured_data_types").value == ["LegalService"]
    assert one(harbour, "seo.pages_with_multiple_h1").value == [
        "https://harbourimmigration.co.uk/about-us/"
    ]
    assert one(harbour, "seo.image_alt_coverage").value == {
        "images": 2,
        "with_alt": 1,
        "ratio": 0.5,
    }
    assert one(harbour, "seo.open_graph").value is False


def test_harbour_company(harbour: dict[str, list[Observation]]) -> None:
    name = one(harbour, "company.name")
    assert name.value == "Harbour Immigration Ltd"
    assert name.evidence_type == EvidenceType.STRUCTURED_DATA
    address = one(harbour, "company.address").value
    assert address == {
        "streetAddress": "1 Cheapside",
        "addressLocality": "London",
        "postalCode": "EC2V 6AA",
        "addressCountry": "GB",
    }
    country = one(harbour, "company.country_hint")
    assert country.value == "GB" and country.confidence == 0.7  # phone beats TLD
    assert one(harbour, "company.founded_year").value == 2009
    assert one(harbour, "company.linkedin_company_url").value == (
        "https://www.linkedin.com/company/harbour-immigration"
    )
    assert "facebook" not in one(harbour, "company.social_profiles").value  # share links ignored
    people = values(harbour, "company.person")
    assert {"name": "Amelia Hart", "title": "Founder and Senior Immigration Adviser"} in people
    assert {"name": "Daniel Okafor", "title": "Head of Operations"} in people
    assert all(p["name"] != "Our Values" for p in people)


def test_harbour_has_no_product_or_hiring_signals(harbour: dict[str, list[Observation]]) -> None:
    assert not [k for k in harbour if k.startswith(("hiring.", "product.login", "product.signup"))]


# --- SaaS startup -------------------------------------------------------------------------


def test_shiplane_technology_and_security(shiplane: dict[str, list[Observation]]) -> None:
    names = {v["name"] for v in values(shiplane, "technology.detected")}
    assert {"Next.js", "Google Analytics", "Stripe", "Vercel"} <= names
    assert "WordPress" not in names
    assert one(shiplane, "website.hsts").value is True
    headers = one(shiplane, "website.security_headers").value
    assert headers["present"] == ["content-security-policy"]
    assert one(shiplane, "website.sitemap").value is True
    assert one(shiplane, "website.copyright_year").value == 2026
    assert "website.stale_copyright" not in shiplane


def test_shiplane_conversion_and_product(shiplane: dict[str, list[Observation]]) -> None:
    assert one(shiplane, "conversion.booking_tool").value == "Calendly"
    assert one(shiplane, "conversion.live_chat").value == "Intercom"
    assert one(shiplane, "conversion.primary_cta").value == "Start free trial"
    assert one(shiplane, "conversion.contact_form").value is False
    assert one(shiplane, "conversion.pricing_page").value is True
    assert one(shiplane, "product.login").value == "https://shiplane.io/login"
    assert one(shiplane, "product.signup").value == "https://shiplane.io/signup"
    assert one(shiplane, "product.subscription_pricing").value.lower() == "per month"
    assert one(shiplane, "product.payments").value == ["Stripe"]
    assert one(shiplane, "product.app_store_links").value == [
        "https://apps.apple.com/app/shiplane/id123"
    ]
    assert one(shiplane, "product.api_docs").value == "https://docs.shiplane.io/api"


def test_shiplane_hiring(shiplane: dict[str, list[Observation]]) -> None:
    assert one(shiplane, "hiring.careers_page").value is True
    board = one(shiplane, "hiring.job_board")
    assert board.value["provider"] == "greenhouse" and board.value["token"] == "shiplane"  # noqa: S105 - job board token
    assert one(shiplane, "hiring.tech_roles").value == [
        "Senior Backend Engineer",
        "Product Manager",
    ]


def test_shiplane_company(shiplane: dict[str, list[Observation]]) -> None:
    assert one(shiplane, "company.name").value == "Shiplane"  # og:site_name preferred
    assert one(shiplane, "seo.structured_data_types").value == ["Organization", "WebSite"]
    assert one(shiplane, "company.social_profiles").value == {
        "x": "https://x.com/shiplane",
        "linkedin": "https://www.linkedin.com/company/shiplane/",
    }


# --- holding page -------------------------------------------------------------------------


def test_holding_page_yields_only_what_is_there() -> None:
    found = run(HOLDING)
    assert one(found, "website.https").value is False
    assert one(found, "seo.home_word_count").value == 2
    assert one(found, "conversion.contact_form").value is False
    assert one(found, "company.name").confidence == 0.5  # from <title> only
    assert not [k for k in found if k.startswith(("technology.", "hiring.", "company.person"))]


def test_a_failing_extractor_does_not_lose_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: object) -> list[Observation]:
        raise RuntimeError("boom")

    monkeypatch.setitem(EXTRACTORS, "seo", broken)
    observations, failed = analyse(*IMMIGRATION)
    assert failed == ["seo"]
    assert any(o.key == "conversion.contact_form" for o in observations)
    assert not any(o.key.startswith("seo.") for o in observations)
