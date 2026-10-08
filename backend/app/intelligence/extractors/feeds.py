"""The company's own news feeds: RSS or Atom links advertised in page heads. Only feeds on the
company's own site are kept; the signals stage reads them for dated announcements."""

from urllib.parse import urljoin, urlsplit

from app.intelligence.types import Area, Observation, Page, SiteContext
from app.research.urls import same_site, site_domain

FEED_TYPES = {"application/rss+xml": "rss", "application/atom+xml": "atom"}
MAX_FEEDS = 2


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    site = site_domain(urlsplit(ctx.home_url).hostname or "")
    out: list[Observation] = []
    seen: set[str] = set()
    for page in pages:
        for node in page.tree.css('link[rel~="alternate"][href]'):
            kind = FEED_TYPES.get((node.attributes.get("type") or "").strip().lower())
            href = (node.attributes.get("href") or "").strip()
            if not kind or not href:
                continue
            url = urljoin(page.url, href)
            if urlsplit(url).scheme not in ("http", "https") or not same_site(url, site):
                continue
            if url in seen or "comments" in url.lower():
                continue
            seen.add(url)
            title = (node.attributes.get("title") or "").strip()
            out.append(
                Observation(
                    Area.COMPANY,
                    "company.feed",
                    {"url": url, "format": kind},
                    page.url,
                    f'<link rel="alternate" type="{node.attributes.get("type")}"'
                    f'{f' title="{title}"' if title else ""} href="{href}">',
                    confidence=0.9,
                )
            )
            if len(out) >= MAX_FEEDS:
                return out
    return out
