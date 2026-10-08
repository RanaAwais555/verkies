"""Technical health of the website (master context §8, Website row)."""

import re
from datetime import UTC, datetime

from app.core.enums import EvidenceType
from app.intelligence.html import is_internal, links, meta
from app.intelligence.types import Area, Observation, Page, SiteContext, excerpt

SECURITY_HEADERS = (
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
)
# "© 2019", "Copyright 2015-2019" (the last year counts).
COPYRIGHT = re.compile(
    r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})",  # noqa: RUF001 - en dash in year ranges
    re.I,
)


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    home = next((p for p in pages if p.category == "home"), pages[0])
    out: list[Observation] = []

    def obs(key: str, value: object, page: Page, text: str, **kw: object) -> None:
        out.append(Observation(Area.WEBSITE, f"website.{key}", value, page.url, text, **kw))  # type: ignore[arg-type]

    https = home.url.startswith("https://")
    obs(
        "https",
        https,
        home,
        f"Homepage served at {home.url}",
        evidence_type=EvidenceType.OTHER,
        confidence=0.95,
    )

    hsts = home.headers.get("strict-transport-security")
    obs(
        "hsts",
        bool(hsts),
        home,
        f"strict-transport-security: {hsts}"
        if hsts
        else f"No Strict-Transport-Security header on {home.url}",
        evidence_type=EvidenceType.HTTP_HEADER,
        confidence=0.95,
    )

    present = [h for h in SECURITY_HEADERS if h in home.headers]
    missing = [h for h in SECURITY_HEADERS if h not in home.headers]
    obs(
        "security_headers",
        {"present": present, "missing": missing},
        home,
        "; ".join(f"{h}: {home.headers[h][:60]}" for h in present)
        or f"None of {', '.join(SECURITY_HEADERS)} set",
        evidence_type=EvidenceType.HTTP_HEADER,
        confidence=0.95,
    )

    viewport = meta(home, "viewport")
    obs(
        "mobile_viewport",
        viewport is not None,
        home,
        f'<meta name="viewport" content="{viewport}">'
        if viewport
        else "No viewport meta tag on the homepage",
        confidence=0.9,
    )

    if not home.rendered and home.bytes:
        obs(
            "homepage_html_kb",
            round(home.bytes / 1024, 1),
            home,
            f"Homepage HTML is {home.bytes} bytes (HTML only, not images or scripts)",
            confidence=0.95,
        )

    obs(
        "robots_txt",
        ctx.robots,
        home,
        f"robots.txt status: {ctx.robots}",
        evidence_type=EvidenceType.OTHER,
        confidence=0.95,
    )
    obs(
        "sitemap",
        bool(ctx.sitemaps),
        home,
        f"Sitemap found at {ctx.sitemaps[0]}" if ctx.sitemaps else "No sitemap.xml found",
        evidence_type=EvidenceType.OTHER,
        confidence=0.9 if ctx.sitemaps else 0.7,
    )

    broken: list[str] = []
    broken_on: Page | None = None
    for page in pages:
        for url, _, _ in links(page):
            status = ctx.statuses.get(url)
            if (
                status is not None
                and status >= 400
                and is_internal(url, ctx.home_url)
                and url not in broken
            ):
                broken.append(url)
                broken_on = broken_on or page
    if broken and broken_on is not None:
        obs(
            "broken_internal_links",
            broken,
            broken_on,
            f"Links on {broken_on.url} lead to pages returning errors: {', '.join(broken[:3])}",
            confidence=0.9,
        )

    years = [int(m.group(1)) for m in COPYRIGHT.finditer(home.text)]
    if years:
        year = max(years)
        match = COPYRIGHT.search(home.text)
        obs(
            "copyright_year",
            year,
            home,
            excerpt(home.text, match.group(0) if match else None, 120),
            confidence=0.85,
        )
        current = datetime.now(UTC).year
        if year <= current - 2:
            obs(
                "stale_copyright",
                current - year,
                home,
                f"Footer copyright says {year}; it is now {current}",
                confidence=0.7,
            )

    last_modified = home.headers.get("last-modified")
    if last_modified:
        obs(
            "last_modified",
            last_modified,
            home,
            f"last-modified: {last_modified}",
            evidence_type=EvidenceType.HTTP_HEADER,
            confidence=0.6,
        )
    return out
