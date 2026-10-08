"""Industry classification from the site's own words and structured data (ICP_SPEC.md §3).

Keyword rules over the homepage, about, services and product pages, plus JSON-LD types. A
classification needs at least three independent keyword hits (or a matching JSON-LD type) and
must beat the runner-up clearly; otherwise the industry stays Unknown. The industry names are
the ones the ICP configuration tiers use.
"""

import re

from app.core.enums import EvidenceType
from app.intelligence.html import json_ld, ld_types
from app.intelligence.types import Area, Observation, Page, SiteContext, excerpt

KEYWORDS: dict[str, tuple[str, ...]] = {
    "saas": (
        "saas",
        "software as a service",
        "subscription software",
        "cloud platform",
        "free trial",
        "per user per month",
        "integrations",
        "api",
    ),
    "ai": (
        "artificial intelligence",
        "machine learning",
        "ai-powered",
        "ai powered",
        "llm",
        "generative ai",
        "ai agent",
    ),
    "fintech": (
        "fintech",
        "payments platform",
        "open banking",
        "lending",
        "neobank",
        "fca authorised",
        "fca-authorised",
        "e-money",
    ),
    "healthtech": (
        "healthtech",
        "digital health",
        "telehealth",
        "patient app",
        "clinical software",
    ),
    "proptech": ("proptech", "property management software", "lettings software", "tenant portal"),
    "edtech": ("edtech", "learning platform", "online courses", "lms", "e-learning"),
    "martech": (
        "martech",
        "marketing automation",
        "customer data platform",
        "email marketing platform",
    ),
    "marketplace": ("marketplace", "buyers and sellers", "list your", "vendors"),
    "software company": ("software development", "custom software", "software company"),
    "immigration": (
        "immigration",
        "visa",
        "settlement",
        "citizenship",
        "home office",
        "sponsor licence",
        "iaa",
        "oisc",
        "indefinite leave",
    ),
    "legal": ("solicitor", "law firm", "legal services", "conveyancing", "litigation", "sra"),
    "recruitment": (
        "recruitment",
        "recruiter",
        "candidates",
        "staffing",
        "talent acquisition",
        "headhunt",
    ),
    "accounting": ("accountant", "accounting", "bookkeeping", "tax return", "payroll", "chartered"),
    "consulting": ("consulting", "consultancy", "advisory", "consultants"),
    "healthcare": ("clinic", "patients", "dental", "physiotherapy", "gp practice", "treatment"),
    "logistics": (
        "logistics",
        "freight",
        "courier",
        "haulage",
        "fleet",
        "dispatch",
        "removals",
        "moving service",
    ),
    "travel technology": ("travel booking", "trip planner", "itinerary", "travel platform"),
    "real estate": (
        "estate agent",
        "real estate",
        "lettings",
        "property for sale",
        "landlords",
        "property",
    ),
    "e-commerce": ("add to basket", "add to cart", "free delivery", "shop now", "checkout"),
    "education": ("school", "tuition", "tutoring", "students", "courses"),
    "construction": ("construction", "builders", "contractor", "refurbishment", "extensions"),
    "automotive": ("car dealer", "garage", "mot", "vehicle servicing", "used cars"),
    "hospitality": ("hotel", "guest house", "bed and breakfast", "events venue"),
    "restaurants": ("restaurant", "menu", "book a table", "takeaway", "cafe"),
    "retail": ("store locator", "in-store", "retail"),
    "fitness": ("gym", "personal training", "fitness classes", "yoga studio"),
    "beauty": ("salon", "beauty", "hairdresser", "spa treatments", "nails"),
}
LD_INDUSTRY = {
    "LegalService": "legal",
    "Attorney": "legal",
    "AccountingService": "accounting",
    "RealEstateAgent": "real estate",
    "Restaurant": "restaurants",
    "Hotel": "hospitality",
    "AutoDealer": "automotive",
    "AutoRepair": "automotive",
    "HealthAndBeautyBusiness": "beauty",
    "BeautySalon": "beauty",
    "ExerciseGym": "fitness",
    "Dentist": "healthcare",
    "MedicalClinic": "healthcare",
    "EmploymentAgency": "recruitment",
    "MovingCompany": "logistics",
    "SoftwareApplication": "saas",
    "EducationalOrganization": "education",
}
MIN_HITS = 3
LEAD_RATIO = 1.5
RELEVANT_CATEGORIES = {"home", "about", "services", "product", "pricing"}


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    relevant = [p for p in pages if p.category in RELEVANT_CATEGORIES] or pages[:1]
    text = " ".join(p.text.lower() for p in relevant)
    scores: dict[str, int] = {}
    first_hit: dict[str, tuple[Page, str]] = {}
    for industry, keywords in KEYWORDS.items():
        for keyword in keywords:
            pattern = re.compile(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])")
            count = len(pattern.findall(text))
            if count:
                scores[industry] = scores.get(industry, 0) + min(count, 5)
                if industry not in first_hit:
                    page = next(
                        (p for p in relevant if pattern.search(p.text.lower())), relevant[0]
                    )
                    first_hit[industry] = (page, keyword)

    out: list[Observation] = []
    for page in pages:
        for item in json_ld(page):
            for ld_type in ld_types(item):
                ld_industry = LD_INDUSTRY.get(ld_type)
                if ld_industry:
                    out.append(
                        Observation(
                            Area.COMPANY,
                            "company.industry",
                            {"name": ld_industry, "basis": "structured_data"},
                            page.url,
                            f"JSON-LD @type {ld_type}",
                            evidence_type=EvidenceType.STRUCTURED_DATA,
                            confidence=0.85,
                        )
                    )
                    scores[ld_industry] = scores.get(ld_industry, 0) + MIN_HITS
                    break
            else:
                continue
            break
        if out:
            break

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if ranked and ranked[0][1] >= MIN_HITS:
        top, top_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0
        already = any(o.value["name"] == top for o in out)
        if top_score >= runner_up * LEAD_RATIO and not already and top in first_hit:
            page, keyword = first_hit[top]
            confidence = round(min(0.85, 0.5 + 0.05 * top_score), 2)
            out.append(
                Observation(
                    Area.COMPANY,
                    "company.industry",
                    {"name": top, "basis": "keywords", "hits": top_score},
                    page.url,
                    excerpt(page.text, keyword),
                    confidence=confidence,
                )
            )
    return out
