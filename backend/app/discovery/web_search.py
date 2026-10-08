"""Turn web search results into candidate companies: one per website, without directories,
social networks, marketplaces, job boards, news or government sites (those are about
companies, not the companies themselves)."""

import re
from urllib.parse import urlsplit

from app.providers.search import SearchResult
from app.research.urls import site_domain

EXCLUDED = frozenset(
    {
        # social and video
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "x.com",
        "twitter.com",
        "tiktok.com",
        "youtube.com",
        "pinterest.com",
        "reddit.com",
        "medium.com",
        "quora.com",
        "threads.net",
        # directories, reviews and maps
        "yelp.com",
        "yelp.co.uk",
        "yell.com",
        "trustpilot.com",
        "google.com",
        "bing.com",
        "tripadvisor.com",
        "tripadvisor.co.uk",
        "checkatrade.com",
        "bark.com",
        "clutch.co",
        "goodfirms.co",
        "crunchbase.com",
        "zoominfo.com",
        "dnb.com",
        "endole.co.uk",
        "companieshouse.gov.uk",
        "company-information.service.gov.uk",
        "opencorporates.com",
        "glassdoor.com",
        "glassdoor.co.uk",
        "indeed.com",
        "indeed.co.uk",
        "reed.co.uk",
        "totaljobs.com",
        "cv-library.co.uk",
        "wikipedia.org",
        "wikidata.org",
        "apple.com",
        "amazon.com",
        "amazon.co.uk",
        "ebay.com",
        "ebay.co.uk",
        "etsy.com",
        "gumtree.com",
        "thomsonlocal.com",
        "192.com",
        "freeindex.co.uk",
        "cylex-uk.co.uk",
        "scoot.co.uk",
        # news and blogs platforms
        "bbc.co.uk",
        "theguardian.com",
        "forbes.com",
        "bloomberg.com",
        "reuters.com",
        "wordpress.com",
        "blogspot.com",
        "substack.com",
        "github.com",
    }
)
EXCLUDED_SUFFIXES = (".gov.uk", ".gov", ".nhs.uk", ".police.uk", ".ac.uk", ".edu", ".sch.uk")
TITLE_SPLIT = re.compile(
    "\\s+[|\u2013\u2014\\-:\u00b7\u2022]\\s+"
)  # "|", en/em dash, "-", ":", middle dot, bullet


GENERIC_TITLE_PARTS = frozenset(
    {"home", "homepage", "home page", "welcome", "index", "official site", "official website"}
)


def company_name(title: str) -> str | None:
    """The likely company name from a page title: the first part of "Name | Tagline" once
    generic parts ("Home", "Welcome") are dropped. Only a label for the reviewer; research
    reads the real name from the site."""
    parts = [p.strip() for p in TITLE_SPLIT.split(title) if p.strip()]
    if not parts:
        return None
    named = [p for p in parts if p.lower() not in GENERIC_TITLE_PARTS]
    return (named or parts)[0][:300]


def excluded(host: str) -> bool:
    """The host or any parent domain is excluded (uk.linkedin.com, www.gov.uk...)."""
    host = host.lower().rstrip(".")
    labels = host.split(".")
    parents = {".".join(labels[i:]) for i in range(len(labels) - 1)}
    return (
        bool(parents & EXCLUDED)
        or host.endswith(EXCLUDED_SUFFIXES)
        or host in {s.lstrip(".") for s in EXCLUDED_SUFFIXES}
    )


def candidates(results: list[SearchResult]) -> list[dict[str, str]]:
    """Rows for a discovery job: {name, website, notes, source_url}, one per site, in result
    order (the provider's ranking)."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in results:
        parts = urlsplit(result.url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            continue
        domain = site_domain(parts.hostname)
        if not domain or domain in seen or excluded(parts.hostname):
            continue
        seen.add(domain)
        rows.append(
            {
                "name": company_name(result.title) or domain,
                # The homepage, keeping a non-default port but never any userinfo.
                "website": f"{parts.scheme}://{parts.hostname}"
                + (f":{parts.port}" if parts.port else "")
                + "/",
                "notes": result.snippet,
                "source_url": result.url,
            }
        )
    return rows
