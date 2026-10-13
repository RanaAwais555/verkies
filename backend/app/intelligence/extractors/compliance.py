"""What a site must show by law or its regulator, and whether the crawled pages show it
(slice 8.2).

Only rules that are public and checkable from the page itself:

* Law firms regulated by the SRA (SRA Transparency Rules): the SRA's digital badge, the SRA
  number, the complaints procedure with the Legal Ombudsman, and published prices for listed
  services, immigration (not asylum) among them.
* UK companies (Companies Act 2006; Company, LLP and Business Names Regulations 2015): the
  registered number on the website.
* Cookies (PECR): tracking scripts on the page with no consent tool found.

A rule applies only when the site says what makes it apply (it names the SRA, it names a
limited company, it loads trackers). "Not found" means not found on the pages crawled, and every
absent observation names how many pages were checked: the crawl reads a bounded set of pages,
so a missing item is a finding to verify, never a verdict.
"""

import re

from app.core.enums import EvidenceType
from app.intelligence.extractors.registration import PATTERNS as COMPANY_NUMBER
from app.intelligence.types import Area, Observation, Page, SiteContext, excerpt, outer

SRA_REGULATED = re.compile(
    r"(?:authorised and )?regulated by the solicitors regulation authority|"
    r"regulated by the SRA\b|\bSRA (?:number|no\.?|id|registration)|"
    r"solicitors regulation authority",
    re.I,
)
# The SRA badge is served from Yoshki's CDN as an iframe or script.
SRA_BADGE = re.compile(r"yoshki\.com|sra-digital-badge|sra_digital_badge", re.I)
SRA_NUMBER = re.compile(
    r"\bSRA\s*(?:registration\s*)?(?:no\.?|number|id|#)\s*[:.]?\s*(\d{5,7})\b|"
    r"solicitors regulation authority[^.]{0,80}?\b(?:no\.?|number|id)\s*[:.]?\s*(\d{5,7})\b",
    re.I,
)
SOLICITORS = re.compile(r"\bsolicitors?\b", re.I)
COMPLAINTS = re.compile(r"\bcomplain", re.I)
OMBUDSMAN = re.compile(r"legal ombudsman", re.I)
IMMIGRATION = re.compile(r"\bimmigration\b|\bvisas?\b|\bsponsor licence\b", re.I)
PRICE = re.compile(r"£\s?\d[\d,]*(?:\.\d{2})?")
PRICE_WORDS = re.compile(r"\b(?:fees?|prices?|pricing|costs?|fixed fee)\b", re.I)
PRICE_LINK = re.compile(r"fee|price|pricing|cost", re.I)
PRICE_WINDOW = 200  # characters either side of an amount that must mention immigration
LEGAL_FORM = re.compile(r"\b[A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*){0,5}\s+(Ltd|Limited|LLP|PLC)\b")
# "Website by", "Designed and developed by", "Powered by": the company after it is a supplier.
CREDIT = re.compile(
    r"\b(?:website|web\s*design|site|design(?:ed)?|develop(?:ed)?|built|powered|hosted|"
    r"created|made|marketing|seo)(?:\s+(?:and|&)\s+\w+)?\s+by\s*[:\-]?\s*$",
    re.I,
)
TRACKERS = {
    "Google Analytics": re.compile(r"google-analytics\.com|googletagmanager\.com/gtag", re.I),
    "Google Tag Manager": re.compile(r"googletagmanager\.com/gtm\.js", re.I),
    "Meta Pixel": re.compile(r"connect\.facebook\.net/[^\"']*/fbevents\.js", re.I),
    "LinkedIn Insight": re.compile(r"snap\.licdn\.com", re.I),
    "Hotjar": re.compile(r"static\.hotjar\.com", re.I),
    "Microsoft Clarity": re.compile(r"clarity\.ms/tag", re.I),
    "TikTok Pixel": re.compile(r"analytics\.tiktok\.com", re.I),
}
CONSENT_TOOLS = {
    "Cookiebot": re.compile(r"cookiebot", re.I),
    "OneTrust": re.compile(r"onetrust|cookielaw\.org", re.I),
    "CookieYes": re.compile(r"cookieyes|cookie-law-info", re.I),
    "Termly": re.compile(r"termly\.io", re.I),
    "iubenda": re.compile(r"iubenda", re.I),
    "Complianz": re.compile(r"complianz", re.I),
    "Osano": re.compile(r"osano\.com", re.I),
    "Usercentrics": re.compile(r"usercentrics", re.I),
    "Civic Cookie Control": re.compile(r"cookiecontrol|civiccomputing", re.I),
    "Quantcast Choice": re.compile(r"quantcast\.mgr|choice\.quantcast", re.I),
    "Google consent mode": re.compile(r"gtag\(\s*['\"]consent['\"]\s*,\s*['\"]default", re.I),
    "Consent banner": re.compile(r"cookie[-_ ]?(?:consent|banner|notice)", re.I),
}


def _checked(pages: list[Page]) -> str:
    return f"Not found on the {len(pages)} pages crawled ({', '.join(p.url for p in pages[:5])})"


def _first(pages: list[Page], pattern: re.Pattern[str], *, html: bool = False) -> Page | None:
    return next((p for p in pages if pattern.search(p.html if html else p.text)), None)


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    home = next((p for p in pages if p.category == "home"), pages[0])
    out: list[Observation] = []
    regulated = _sra_regulated(pages, home)
    if regulated is not None:
        out.extend(_sra(pages, home, regulated))
    out.extend(_company_details(pages, home))
    out.extend(_cookie_consent(pages, home))
    return out


def _title_and_heading(page: Page) -> str:
    title = page.tree.css_first("title")
    heading = page.tree.css_first("h1")
    return " ".join(n.text() for n in (title, heading) if n is not None)


def _sra_regulated(pages: list[Page], home: Page) -> Observation | None:
    """Why the SRA's rules apply, if they do: the site names the SRA, shows its badge or an SRA
    number, or calls itself solicitors (a firm of solicitors in England and Wales must be
    authorised by the SRA). A firm that calls itself solicitors and shows nothing of the SRA is
    exactly the gap worth finding, so the title and main heading count too."""
    if page := _first(pages, SRA_REGULATED):
        basis, text = "names the SRA", excerpt(page.text, "regulat", 200)
    elif page := _first(pages, SRA_BADGE, html=True):
        basis, text = "shows the SRA badge", "SRA digital badge code on the page"
    elif page := _first(pages, SRA_NUMBER):
        basis, text = "shows an SRA number", excerpt(page.text, "SRA", 160)
    elif SOLICITORS.search(_title_and_heading(home)):
        page, basis = home, "describes itself as solicitors"
        text = f"Title and main heading: {_title_and_heading(home)[:200]}"
    else:
        return None
    return Observation(
        Area.COMPLIANCE,
        "compliance.sra_regulated",
        True,
        page.url,
        f"{basis[0].upper()}{basis[1:]}: {text}",
        confidence=0.9 if basis != "describes itself as solicitors" else 0.75,
    )


def _sra(pages: list[Page], home: Page, regulated: Observation) -> list[Observation]:
    """SRA Transparency Rules, for a site the SRA's rules apply to."""
    out = [regulated]
    badge = _first(pages, SRA_BADGE, html=True)
    badge_node = badge.tree.css_first("iframe[src*=yoshki], script[src*=yoshki]") if badge else None
    out.append(
        Observation(
            Area.COMPLIANCE,
            "compliance.sra_badge",
            badge is not None,
            badge.url if badge else home.url,
            (outer(badge_node, 200) if badge_node else "SRA digital badge code on the page")
            if badge
            else f"No SRA digital badge. {_checked(pages)}",
            evidence_type=EvidenceType.PAGE_CONTENT,
            confidence=0.9 if badge else 0.7,
        )
    )
    number_page, number = None, None
    for page in pages:
        if match := SRA_NUMBER.search(page.text):
            number_page, number = page, match.group(1) or match.group(2)
            break
    out.append(
        Observation(
            Area.COMPLIANCE,
            "compliance.sra_number",
            {"number": number} if number else False,
            number_page.url if number_page else home.url,
            excerpt(number_page.text, number, 160)
            if number_page and number
            else f"No SRA number shown. {_checked(pages)}",
            confidence=0.9 if number else 0.7,
        )
    )
    complaints = next(
        (p for p in pages if COMPLAINTS.search(p.text) and OMBUDSMAN.search(p.text)), None
    )
    out.append(
        Observation(
            Area.COMPLIANCE,
            "compliance.complaints_procedure",
            complaints is not None,
            complaints.url if complaints else home.url,
            excerpt(complaints.text, "Legal Ombudsman", 200)
            if complaints
            else f"No complaints procedure naming the Legal Ombudsman. {_checked(pages)}",
            confidence=0.85 if complaints else 0.65,
        )
    )
    immigration = _first(pages, IMMIGRATION)
    if immigration is not None:
        found = next(
            ((p, amount) for p in _price_pages(pages) if (amount := _immigration_price(p))), None
        )
        priced = found[0] if found else None
        other = next(iter(_price_pages(pages)), None)
        if found:
            text = excerpt(found[0].text, found[1], 200)
        elif other:
            text = (
                f"Immigration work is offered; the fees page ({other.url}) gives prices but "
                f"not for immigration work."
            )
        else:
            text = "Immigration work is offered, but no fees or prices were found. " + _checked(
                pages
            )
        out.append(
            Observation(
                Area.COMPLIANCE,
                "compliance.price_information",
                {"service": "immigration", "published": priced is not None},
                priced.url if priced else (other or immigration).url,
                text,
                confidence=0.75 if priced else 0.6,
            )
        )
    return out


def _immigration_price(page: Page) -> str | None:
    """An amount stated near the words immigration or visa (a menu elsewhere on the page that
    lists "Immigration" does not make a debt-recovery fee an immigration price). Returns the
    text from that word on, so the evidence shows the immigration prices themselves."""
    for match in PRICE.finditer(page.text):
        start = max(0, match.start() - PRICE_WINDOW)
        window = page.text[start : match.end() + PRICE_WINDOW]
        if word := IMMIGRATION.search(window):
            return window[word.start() : word.start() + 60]
    return None


def _price_pages(pages: list[Page]) -> list[Page]:
    """Pages that state amounts as fees or prices (a fees page, or prices in the text)."""
    return [
        page
        for page in pages
        if PRICE.search(page.text)
        and (
            page.category == "pricing"
            or PRICE_WORDS.search(page.text)
            or PRICE_LINK.search(page.url)
        )
    ]


def _company_details(pages: list[Page], home: Page) -> list[Observation]:
    """A site naming a limited company or LLP should show its registered number. A company
    named in a credit ("Website by Webist Ltd") is the web agency, not the business."""
    named = next(
        (
            (p, m)
            for p in pages
            for m in LEGAL_FORM.finditer(p.text)
            if not CREDIT.search(p.text[max(0, m.start() - 60) : m.start()])
        ),
        None,
    )
    if named is None:
        return []
    page, match = named
    shown = next(
        (q for q in pages if any(pattern.search(q.text) for pattern in COMPANY_NUMBER)), None
    )
    return [
        Observation(
            Area.COMPLIANCE,
            "compliance.company_number_shown",
            shown is not None,
            shown.url if shown else page.url,
            excerpt(shown.text, "regist", 160)
            if shown
            else f'The site names "{match.group(0)}" but shows no registered company number. '
            + _checked(pages),
            confidence=0.85 if shown else 0.65,
        )
    ]


def _cookie_consent(pages: list[Page], home: Page) -> list[Observation]:
    """Trackers loaded with no consent tool in sight. Static HTML cannot show whether a tracker
    waits for consent, so a found tool is reported, not certified."""
    trackers = sorted({n for n, rx in TRACKERS.items() for p in pages if rx.search(p.html)})
    if not trackers:
        return []
    tool = next((n for n, rx in CONSENT_TOOLS.items() for p in pages if rx.search(p.html)), None)
    return [
        Observation(
            Area.COMPLIANCE,
            "compliance.cookie_consent",
            {"trackers": trackers, "consent_tool": tool},
            home.url,
            f"Trackers: {', '.join(trackers)}; consent tool: {tool}"
            if tool
            else f"Trackers loaded ({', '.join(trackers)}) with no cookie consent tool found. "
            + _checked(pages),
            evidence_type=EvidenceType.TECHNOLOGY_FINGERPRINT,
            confidence=0.8 if tool else 0.7,
        )
    ]
