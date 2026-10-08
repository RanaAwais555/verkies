"""What kind of site this is: parked, closed, pre-launch, a personal/freelancer site, or an
agency. These drive the negative-ICP rules (ICP_SPEC.md §5); each needs explicit wording on
the page, so an ordinary business site produces none of them."""

import re

from app.intelligence.types import Area, Observation, Page, SiteContext, excerpt

PARKED = re.compile(
    r"\b(this domain (?:is|may be) for sale|buy this domain|domain (?:is )?parked|"
    r"parked (?:free|domain)|courtesy of godaddy|sedoparking|dan\.com|hugedomains)\b",
    re.I,
)
UNDER_CONSTRUCTION = re.compile(
    r"\b(coming soon|under construction|website (?:is )?(?:launching|coming) soon|"
    r"site is being built)\b",
    re.I,
)
CLOSED = re.compile(
    r"\b(ceased trading|permanently closed|we have (?:now )?closed|no longer trading|"
    r"has closed (?:its|our) doors|company (?:has been )?dissolved)\b",
    re.I,
)
WAITLIST = re.compile(
    r"\b(join (?:the|our) waitlist|join the wait list|request early access|get early access|"
    r"early access|private beta|launching soon|be the first to know)\b",
    re.I,
)
PERSONAL = re.compile(
    r"\b(hire me|i'?m available for (?:freelance|work|hire)|open to work|my portfolio|"
    r"freelance (?:web )?(?:developer|designer)|i am a (?:freelance|self-employed)|"
    r"view my (?:work|cv|resume)|download my (?:cv|resume))\b",
    re.I,
)
AGENCY = re.compile(
    r"\b((?:digital|web|creative|marketing|seo|software development|branding|design) agency|"
    r"we build (?:websites|apps|software) for|our clients include|"
    r"white[- ]label (?:services|partner)|"
    r"web design (?:and|&) development (?:services|company))\b",
    re.I,
)


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    home = next((p for p in pages if p.category == "home"), pages[0])
    out: list[Observation] = []
    words = len(home.text.split())

    parked = PARKED.search(home.text)
    if parked:
        out.append(
            Observation(
                Area.WEBSITE,
                "website.holding_page",
                "parked",
                home.url,
                excerpt(home.text, parked.group(0)),
                confidence=0.9,
            )
        )
    elif words < 120 and (building := UNDER_CONSTRUCTION.search(home.text)):
        out.append(
            Observation(
                Area.WEBSITE,
                "website.holding_page",
                "coming_soon",
                home.url,
                excerpt(home.text, building.group(0)),
                confidence=0.85,
            )
        )

    for key, pattern, confidence in (
        ("company.closed_notice", CLOSED, 0.85),
        ("company.personal_site_signals", PERSONAL, 0.75),
        ("company.agency_signals", AGENCY, 0.7),
        ("product.waitlist", WAITLIST, 0.8),
    ):
        hits: list[str] = []
        first: Page | None = None
        for page in pages:
            for match in pattern.finditer(page.text):
                phrase = match.group(0).lower()
                if phrase not in hits:
                    hits.append(phrase)
                    first = first or page
        if hits and first is not None:
            area = Area.PRODUCT if key.startswith("product.") else Area.COMPANY
            out.append(
                Observation(
                    area,
                    key,
                    hits[:8],
                    first.url,
                    excerpt(first.text, hits[0]),
                    confidence=confidence,
                )
            )
    return out
