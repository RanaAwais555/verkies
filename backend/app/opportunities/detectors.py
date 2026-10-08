"""Opportunity detection (master context §9): observations -> commercial opportunities.

Each detector is a small rule that needs specific, evidenced observations and states the
problem in business terms, never as a bare technical fact. It returns the evidence IDs it
relied on, so every candidate can show why it exists. Detectors never fire on a single weak
signal; most need two or more independent ones.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from app.intelligence.facts import Facts

SERVICE_INDUSTRIES = frozenset(
    {
        "immigration",
        "legal",
        "recruitment",
        "accounting",
        "consulting",
        "healthcare",
        "logistics",
        "real estate",
        "education",
        "construction",
        "automotive",
        "hospitality",
        "restaurants",
        "retail",
        "fitness",
        "beauty",
        "professional services",
    }
)
APPOINTMENT_INDUSTRIES = frozenset(
    {
        "immigration",
        "legal",
        "accounting",
        "consulting",
        "healthcare",
        "real estate",
        "automotive",
        "education",
        "fitness",
        "beauty",
    }
)
PRODUCT_INDUSTRIES = frozenset(
    {
        "saas",
        "ai",
        "fintech",
        "healthtech",
        "proptech",
        "edtech",
        "martech",
        "marketplace",
        "software company",
        "travel technology",
    }
)
ANALYTICS = frozenset(
    {
        "Google Analytics",
        "Google Tag Manager",
        "Hotjar",
        "Microsoft Clarity",
        "Meta Pixel",
        "LinkedIn Insight",
        "HubSpot",
    }
)
MODERN_FRAMEWORKS = frozenset({"Next.js", "Nuxt", "Gatsby", "React", "Vue.js", "Angular", "Svelte"})


@dataclass
class Candidate:
    category: str  # opportunity category key (master context §9)
    title: str
    problem: str
    confidence: float
    rule_key: str
    evidence_ids: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)  # observation keys used


Detector = Callable[[Facts], Candidate | None]


def industries(facts: Facts) -> list[str]:
    return [f.value["name"] for f in facts.all("company.industry")]


def _industry_label(facts: Facts) -> str:
    # The site's own words are more specific than a generic schema.org type.
    ranked = sorted(facts.all("company.industry"), key=lambda f: f.value.get("basis") != "keywords")
    if not ranked:
        return "this business"
    name = ranked[0].value["name"]
    return f"{'an' if name[0] in 'aeiou' else 'a'} {name} business"


def _wordpress_version(facts: Facts) -> tuple[int, ...] | None:
    generator = str(facts.value("technology.generator", ""))
    if generator.lower().startswith("wordpress"):
        parts = generator.split()[-1].split(".")
        try:
            return tuple(int(p) for p in parts if p.isdigit())
        except ValueError:
            return None
    return None


def website_rebuild(facts: Facts) -> Candidate | None:
    signals: list[tuple[str, str]] = []
    if (stale := facts.value("website.stale_copyright")) and stale >= 2:
        year = facts.value("website.copyright_year")
        signals.append(("website.stale_copyright", f"the footer copyright still says {year}"))
    version = _wordpress_version(facts)
    if version and version < (6,):
        signals.append(
            (
                "technology.generator",
                f"it runs an outdated WordPress ({facts.value('technology.generator')})",
            )
        )
    if facts.is_absent("website.mobile_viewport"):
        signals.append(("website.mobile_viewport", "it is not set up for mobile screens"))
    if facts.value("website.https") is False:
        signals.append(("website.https", "it is not served over HTTPS"))
    if facts.present("website.broken_internal_links"):
        signals.append(("website.broken_internal_links", "some of its own links are broken"))
    if facts.has("seo.home_h1") and facts.value("seo.home_h1") is None:
        signals.append(("seo.home_h1", "the homepage has no main heading"))
    if len(signals) < 2:
        return None
    reasons = "; ".join(text for _, text in signals)
    return Candidate(
        category="website_rebuild",
        title="Website rebuild",
        problem=(
            f"The website shows signs of neglect ({reasons}). An unmaintained site undermines "
            f"trust and is hard to change; a rebuilt, maintainable site is a likely need."
        ),
        confidence=round(min(0.85, 0.45 + 0.1 * len(signals)), 2),
        rule_key="website_rebuild.neglect_signals",
        evidence_ids=facts.evidence(*(k for k, _ in signals), "website.copyright_year"),
        signals=[k for k, _ in signals],
    )


def structured_intake(facts: Facts) -> Candidate | None:
    """The Wesbridge pattern: a service firm taking enquiries through a generic form or email,
    with no booking, client portal or self-service."""
    if not SERVICE_INDUSTRIES.intersection(industries(facts)):
        return None
    has_intake = facts.is_true("conversion.contact_form") or facts.present(
        "conversion.email_addresses"
    )
    if not has_intake or facts.present("conversion.booking_tool"):
        return None
    if facts.present("product.portal") or facts.present("product.login"):
        return None
    signals = ["company.industry", "conversion.booking_tool"]
    confidence = 0.55
    route = "a generic contact form" if facts.is_true("conversion.contact_form") else "email"
    if facts.is_true("conversion.contact_form"):
        signals += ["conversion.contact_form", "conversion.contact_form_fields"]
        confidence += 0.1
    else:
        signals.append("conversion.email_addresses")
    if facts.is_absent("conversion.live_chat"):
        signals.append("conversion.live_chat")
        confidence += 0.05
    return Candidate(
        category="crm",
        title="Structured enquiry, CRM and client portal",
        problem=(
            f"Enquiries reach {_industry_label(facts)} through {route}, with no online "
            f"booking, client portal or self-service found on the site. That usually means "
            f"manual intake, retyping and chasing. A structured enquiry, CRM and client-portal "
            f"workflow is a plausible fit."
        ),
        confidence=round(min(confidence, 0.75), 2),
        rule_key="crm.manual_intake",
        evidence_ids=facts.evidence(*signals),
        signals=signals,
    )


def booking_system(facts: Facts) -> Candidate | None:
    if not APPOINTMENT_INDUSTRIES.intersection(industries(facts)):
        return None
    if not facts.is_absent("conversion.booking_tool"):
        return None
    if not (facts.present("conversion.phone_numbers") or facts.is_true("conversion.contact_form")):
        return None
    return Candidate(
        category="booking_system",
        title="Online booking",
        problem=(
            f"Consultations are arranged by phone or form; no online booking was found. For "
            f"{_industry_label(facts)} an online booking and reminder flow removes back-and-forth."
        ),
        confidence=0.5,
        rule_key="booking_system.no_online_booking",
        evidence_ids=facts.evidence(
            "company.industry",
            "conversion.booking_tool",
            "conversion.phone_numbers",
            "conversion.contact_form",
        ),
        signals=["company.industry", "conversion.booking_tool"],
    )


def conversion_path(facts: Facts) -> Candidate | None:
    signals: list[tuple[str, str]] = []
    if facts.has("conversion.home_ctas") and facts.value("conversion.home_ctas") == []:
        signals.append(("conversion.home_ctas", "the homepage has no clear call to action"))
    if (
        facts.is_absent("conversion.contact_form")
        and facts.is_absent("conversion.booking_tool")
        and facts.is_absent("conversion.live_chat")
    ):
        signals.append(("conversion.contact_form", "there is no enquiry form, booking or chat"))
    no_proof = not facts.has("conversion.testimonials") and not facts.has(
        "conversion.reviews_widget"
    )
    if no_proof and signals:
        signals.append(("conversion.testimonials", "no testimonials or reviews were found"))
    if not signals or (len(signals) == 1 and signals[0][0] == "conversion.testimonials"):
        return None
    reasons = "; ".join(t for _, t in signals)
    return Candidate(
        category="conversion_optimization",
        title="Conversion path",
        problem=(
            f"Visitors have no easy next step ({reasons}). A clearer path from visit to "
            f"enquiry would turn more existing traffic into leads."
        ),
        confidence=round(min(0.75, 0.45 + 0.1 * len(signals)), 2),
        rule_key="conversion_optimization.weak_path",
        evidence_ids=facts.evidence(*(k for k, _ in signals)),
        signals=[k for k, _ in signals],
    )


def seo_gaps(facts: Facts) -> Candidate | None:
    issues: list[tuple[str, str]] = []
    if facts.has("seo.home_meta_description") and facts.value("seo.home_meta_description") is None:
        issues.append(("seo.home_meta_description", "no homepage meta description"))
    if facts.present("seo.pages_missing_meta_description"):
        issues.append(("seo.pages_missing_meta_description", "pages without meta descriptions"))
    if facts.value("seo.structured_data_types") == []:
        issues.append(("seo.structured_data_types", "no structured data"))
    if facts.present("seo.pages_without_h1"):
        issues.append(("seo.pages_without_h1", "pages without a main heading"))
    if facts.is_absent("website.sitemap"):
        issues.append(("website.sitemap", "no sitemap"))
    words = facts.value("seo.home_word_count")
    if isinstance(words, int) and words < 250:
        issues.append(("seo.home_word_count", f"a thin homepage ({words} words)"))
    title = facts.value("seo.home_title")
    if isinstance(title, dict) and not title.get("in_range"):
        issues.append(("seo.home_title", "a homepage title of poor length"))
    alt = facts.value("seo.image_alt_coverage")
    if isinstance(alt, dict) and alt.get("images", 0) >= 3 and alt.get("ratio", 1) < 0.5:
        issues.append(("seo.image_alt_coverage", "most images lack alt text"))
    if len(issues) < 3:
        return None
    return Candidate(
        category="seo",
        title="Search visibility",
        problem=(
            f"Basic search signals are missing ({'; '.join(t for _, t in issues)}). The site is "
            f"unlikely to be found for the questions its customers search; SEO and content work "
            f"is a plausible opportunity."
        ),
        confidence=round(min(0.8, 0.4 + 0.07 * len(issues)), 2),
        rule_key="seo.basic_gaps",
        evidence_ids=facts.evidence(*(k for k, _ in issues)),
        signals=[k for k, _ in issues],
    )


def pre_launch_product(facts: Facts) -> Candidate | None:
    waitlist = facts.present("product.waitlist")
    coming_soon = facts.value("website.holding_page") == "coming_soon"
    if not (waitlist or coming_soon) or facts.present("product.login"):
        return None
    signals = [k for k in ("product.waitlist", "website.holding_page") if facts.has(k)]
    return Candidate(
        category="mvp_development",
        title="MVP build",
        problem=(
            "The company is pre-launch (waitlist or coming-soon page, no product sign-in yet). "
            "Getting a first version live quickly is likely the immediate need."
        ),
        confidence=0.6 if waitlist else 0.45,
        rule_key="mvp_development.pre_launch",
        evidence_ids=facts.evidence(*signals),
        signals=signals,
    )


def engineering_capacity(facts: Facts) -> Candidate | None:
    roles = facts.value("hiring.tech_roles")
    if not roles:
        return None
    signals = ["hiring.tech_roles"] + [k for k in ("hiring.job_board",) if facts.has(k)]
    # A product company hiring engineers is building its product; others are building tools.
    product = bool(PRODUCT_INDUSTRIES.intersection(industries(facts)))
    return Candidate(
        category="saas_development" if product else "internal_tools",
        title="Engineering capacity",
        problem=(
            f"They are hiring for {', '.join(roles[:3])}: building is under way and capacity "
            f"is short now. An external product team can deliver while hiring continues."
        ),
        confidence=0.65 if len(roles) > 1 else 0.55,
        rule_key="engineering_capacity.hiring_engineers",
        evidence_ids=facts.evidence(*signals),
        signals=signals,
    )


def legacy_application(facts: Facts) -> Candidate | None:
    if not (facts.present("product.login") or facts.present("product.portal")):
        return None
    techs = facts.technologies()
    legacy = [n for n in ("ASP.NET", "jQuery") if n in techs]
    if not legacy or MODERN_FRAMEWORKS.intersection(techs):
        return None
    signals = ["product.login", "product.portal", "technology.detected"]
    return Candidate(
        category="application_modernization",
        title="Application modernisation",
        problem=(
            f"Customers sign in to an application built on {', '.join(legacy)} with no modern "
            f"front-end framework detected. Modernising it is a likely medium-term need."
        ),
        confidence=0.45,
        rule_key="application_modernization.legacy_stack",
        evidence_ids=facts.evidence(*signals),
        signals=signals,
    )


def mobile_gap(facts: Facts) -> Candidate | None:
    if not PRODUCT_INDUSTRIES.intersection(industries(facts)):
        return None
    if not (facts.present("product.login") and facts.present("product.subscription_pricing")):
        return None
    if facts.present("product.app_store_links"):
        return None
    signals = ["company.industry", "product.login", "product.subscription_pricing"]
    return Candidate(
        category="mobile_application",
        title="Mobile app",
        problem=(
            "A subscription product with a web sign-in and no app in the App Store or Google "
            "Play. A companion mobile app may be on their roadmap."
        ),
        confidence=0.4,
        rule_key="mobile_application.web_only_product",
        evidence_ids=facts.evidence(*signals),
        signals=signals,
    )


def measurement_gap(facts: Facts) -> Candidate | None:
    if ANALYTICS.intersection(facts.technologies()) or not facts.has("conversion.contact_form"):
        return None
    if not facts.present("conversion.home_ctas"):
        return None
    signals = ["technology.detected", "conversion.home_ctas"]
    return Candidate(
        category="analytics",
        title="Analytics and tracking",
        problem=(
            "No analytics or tracking scripts were detected, so the business cannot see which "
            "pages or channels bring enquiries."
        ),
        confidence=0.4,
        rule_key="analytics.no_tracking",
        evidence_ids=facts.evidence("conversion.home_ctas"),
        signals=signals,
    )


DETECTORS: tuple[Detector, ...] = (
    structured_intake,
    website_rebuild,
    conversion_path,
    booking_system,
    seo_gaps,
    pre_launch_product,
    engineering_capacity,
    legacy_application,
    mobile_gap,
    measurement_gap,
)


def detect(facts: Facts) -> list[Candidate]:
    """All candidates, strongest first. Agencies, parked and closed sites get none: the
    negative-ICP engine handles them, and selling to them would be noise."""
    if facts.has("company.closed_notice") or facts.value("website.holding_page") == "parked":
        return []
    if facts.value("website.holding_page") == "coming_soon":
        # A placeholder page says nothing about a website to rebuild; only pre-launch applies.
        launch = pre_launch_product(facts)
        return [launch] if launch else []
    found = [c for c in (d(facts) for d in DETECTORS) if c is not None]
    return sorted(found, key=lambda c: -c.confidence)
