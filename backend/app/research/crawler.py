"""Decides what to fetch for one company website, and in what order (ARCHITECTURE.md §5).

robots.txt first, then the homepage, sitemaps, and a bounded set of high-value pages (about,
team, services, contact, pricing, careers, login/signup, blog, case studies, product). Pages
whose static HTML is too thin are rendered with JavaScript. The crawl stops at any limit
(pages, bytes, time), on cancellation, or when the site pushes back (403/429), and records why.

The crawler holds no I/O of its own: fetching, caching and storage come in through
PageSource, and every outcome is reported through on_page, so it can be tested with fakes.
"""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.core.enums import PageKind
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.fetch.types import FetchResult
from app.research.robots import RobotsPolicy
from app.research.urls import normalise_url, same_site, site_domain

# Category -> path/link-text keywords, in priority order.
CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("about", ("about", "company", "who-we-are", "our-story")),
    ("team", ("team", "people", "leadership", "founders", "management")),
    ("services", ("services", "solutions", "what-we-do", "offerings", "expertise")),
    ("product", ("product", "features", "platform", "how-it-works")),
    ("pricing", ("pricing", "plans", "price", "fees")),
    ("contact", ("contact", "get-in-touch", "enquir", "inquir", "quote", "book", "booking")),
    ("careers", ("careers", "jobs", "join-us", "hiring", "vacancies", "work-with-us")),
    (
        "account",
        (
            "login",
            "log-in",
            "signin",
            "sign-in",
            "signup",
            "sign-up",
            "register",
            "dashboard",
            "portal",
            "app",
        ),
    ),
    ("work", ("case-stud", "clients", "portfolio", "work", "customers", "success")),
    ("blog", ("blog", "news", "insights", "press", "articles", "resources")),
]
MAX_PER_CATEGORY = 2
MAX_SITEMAPS = 4
MAX_SITEMAP_URLS = 1000
ASSET_SUFFIXES = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".zip",
    ".mp4",
    ".mp3",
    ".css",
    ".js",
    ".json",
    ".xml",
    ".txt",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
)
THIN_TEXT_CHARS = 400
APP_ROOT = re.compile(r'<div[^>]+id=["\'](root|__next|app|__nuxt)["\'][^>]*>\s*</div>', re.I)
ROBOTS_TYPES = frozenset({"text/plain", "text/html"})
SITEMAP_TYPES = frozenset({"application/xml", "text/xml", "text/plain"})
PUSHBACK_STATUSES = frozenset({403, 429})


@dataclass(frozen=True)
class Fetched:
    result: FetchResult
    from_cache: bool = False
    raw_response_id: str | None = None


class PageSource(Protocol):
    async def fetch(self, url: str, *, content_types: frozenset[str] | None = None) -> Fetched: ...

    async def render(self, url: str) -> Fetched | None:
        """Rendered page, or None when rendering is disabled or unavailable."""


@dataclass
class PageOutcome:
    kind: PageKind
    url: str
    discovered_via: str
    category: str | None = None
    fetched: Fetched | None = None
    rendered: bool = False
    title: str | None = None
    canonical_url: str | None = None
    duplicate_of_url: str | None = None
    skip_reason: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class CrawlLimits:
    max_pages: int = 15
    max_total_bytes: int = 15 * 1024 * 1024
    wall_clock_seconds: float = 120.0
    min_interval_seconds: float = 1.0
    concurrency: int = 2


@dataclass
class CrawlReport:
    start_url: str
    site: str
    pages_fetched: int = 0
    bytes_fetched: int = 0
    robots: str = "missing"
    sitemaps: list[str] = field(default_factory=list)
    limits_hit: list[str] = field(default_factory=list)
    stopped_reason: str | None = None


class CrawlCancelled(Exception):
    pass


class _Stop(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


class Crawler:
    def __init__(
        self,
        source: PageSource,
        limits: CrawlLimits,
        *,
        on_page: Callable[[PageOutcome], Awaitable[None]],
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
        is_cancelled: Callable[[], Awaitable[bool]] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.source = source
        self.limits = limits
        self.on_page = on_page
        self.on_progress = on_progress
        self.is_cancelled = is_cancelled
        self.clock = clock
        self.sleep = sleep
        self._started = 0.0
        self._last_request = -1e9
        self._interval = limits.min_interval_seconds
        self._spacing = asyncio.Lock()
        self._seen_final: dict[str, str] = {}
        self._report: CrawlReport | None = None

    async def crawl(self, start_url: str) -> CrawlReport:
        self._started = self.clock()
        site = site_domain(urlsplit(start_url).hostname or "")
        report = self._report = CrawlReport(start_url=start_url, site=site)
        try:
            robots = await self._robots(start_url)
            homepage = await self._homepage(start_url, robots)
            if homepage is None:
                return report
            home_url, links = homepage
            sitemap_urls = await self._sitemaps(home_url, robots)
            plan = select_pages(
                links,
                sitemap_urls,
                site=report.site,
                exclude={home_url},
                limit=self.limits.max_pages - 1,
            )
            await self._progress(1, len(plan) + 1)
            await self._fetch_pages(plan, robots)
        except _Stop as stop:
            report.stopped_reason = stop.reason
            if stop.reason not in report.limits_hit:
                report.limits_hit.append(stop.reason)
        return report

    # --- steps ----------------------------------------------------------------------------

    async def _robots(self, start_url: str) -> RobotsPolicy:
        assert self._report is not None
        parts = urlsplit(start_url)
        url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        outcome = PageOutcome(kind=PageKind.ROBOTS, url=url, discovered_via="robots")
        try:
            fetched = await self._get(url, content_types=ROBOTS_TYPES)
        except ProviderError as exc:
            # RFC 9309: unreachable robots.txt means do not crawl.
            outcome.skip_reason, outcome.error = f"fetch_failed:{exc.code}", exc.message
            await self.on_page(outcome)
            policy = RobotsPolicy.deny_all("unreachable")
        else:
            outcome.fetched = fetched
            await self.on_page(outcome)
            status = fetched.result.status
            if status == 200:
                policy = RobotsPolicy.parse(fetched.result.text())
            elif 400 <= status < 500 and status != 429:
                policy = RobotsPolicy(source="missing")  # RFC 9309: 4xx means no rules
            else:
                policy = RobotsPolicy.deny_all("unreachable")
        delay = policy.crawl_delay()
        if delay is not None:
            self._interval = max(self._interval, delay)
        self._report.robots = policy.source
        return policy

    async def _homepage(
        self, url: str, robots: RobotsPolicy
    ) -> tuple[str, list[tuple[str, str]]] | None:
        assert self._report is not None
        outcome = PageOutcome(kind=PageKind.PAGE, url=url, discovered_via="start", category="home")
        if not robots.allows(url):
            outcome.skip_reason = "robots_disallowed"
            await self.on_page(outcome)
            self._report.stopped_reason = "robots_disallowed_homepage"
            return None
        html = await self._fetch_page(outcome)
        if html is None:
            self._report.stopped_reason = self._report.stopped_reason or "homepage_unavailable"
            return None
        final = outcome.fetched.result.final_url if outcome.fetched else url
        # Follow a site-level redirect (acme.com -> acme.co.uk): crawl the site actually served.
        self._report.site = site_domain(urlsplit(final).hostname or "")
        return final, extract_links(html, final)

    async def _sitemaps(self, home_url: str, robots: RobotsPolicy) -> list[str]:
        assert self._report is not None
        parts = urlsplit(home_url)
        queue = [u for u in (normalise_url(s) for s in robots.sitemaps) if u] or [
            f"{parts.scheme}://{parts.netloc}/sitemap.xml"
        ]
        urls: list[str] = []
        fetched_count = 0
        while queue and fetched_count < MAX_SITEMAPS and len(urls) < MAX_SITEMAP_URLS:
            sitemap_url = queue.pop(0)
            if not same_site(sitemap_url, self._report.site) or not robots.allows(sitemap_url):
                continue
            fetched_count += 1
            outcome = PageOutcome(kind=PageKind.SITEMAP, url=sitemap_url, discovered_via="sitemap")
            try:
                fetched = await self._get(sitemap_url, content_types=SITEMAP_TYPES)
            except ProviderError as exc:
                outcome.skip_reason, outcome.error = f"fetch_failed:{exc.code}", exc.message
                await self.on_page(outcome)
                continue
            outcome.fetched = fetched
            await self.on_page(outcome)
            if fetched.result.status != 200:
                continue
            self._report.sitemaps.append(sitemap_url)
            children, pages = parse_sitemap(fetched.result.text())
            queue.extend(c for c in children if c not in queue)
            urls.extend(pages[: MAX_SITEMAP_URLS - len(urls)])
        return urls

    async def _fetch_pages(self, plan: list[tuple[str, str, str]], robots: RobotsPolicy) -> None:
        semaphore = asyncio.Semaphore(self.limits.concurrency)
        done = 1
        total = len(plan) + 1

        async def one(url: str, via: str, category: str) -> None:
            nonlocal done
            async with semaphore:
                outcome = PageOutcome(
                    kind=PageKind.PAGE, url=url, discovered_via=via, category=category
                )
                if not robots.allows(url):
                    outcome.skip_reason = "robots_disallowed"
                    await self.on_page(outcome)
                else:
                    await self._fetch_page(outcome)
                done += 1
                await self._progress(done, total)

        tasks = [asyncio.create_task(one(*item)) for item in plan]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _fetch_page(self, outcome: PageOutcome) -> str | None:
        """Fetch (and if needed render) one page, report it, and return its HTML."""
        assert self._report is not None
        try:
            fetched = await self._get(outcome.url)
        except ProviderError as exc:
            outcome.skip_reason, outcome.error = f"fetch_failed:{exc.code}", exc.message
            await self.on_page(outcome)
            return None
        outcome.fetched = fetched
        result = fetched.result
        if result.status in PUSHBACK_STATUSES:
            outcome.skip_reason = f"http_{result.status}"
            await self.on_page(outcome)
            raise _Stop(f"site_refused_{result.status}")
        if result.status != 200 or not result.is_html:
            outcome.skip_reason = f"http_{result.status}" if result.status != 200 else "not_html"
            await self.on_page(outcome)
            return None
        html = result.text()
        if is_thin(html):
            rendered = await self._render(outcome.url)
            if rendered is not None:
                outcome.fetched, outcome.rendered, html = rendered, True, rendered.result.text()
        outcome.title, outcome.canonical_url = page_meta(html, result.final_url)
        key = (
            outcome.canonical_url
            if outcome.canonical_url and same_site(outcome.canonical_url, self._report.site)
            else result.final_url
        )
        if key in self._seen_final:
            outcome.duplicate_of_url = self._seen_final[key]
        else:
            self._seen_final[key] = outcome.url
            self._report.pages_fetched += 1
        await self.on_page(outcome)
        return html

    async def _render(self, url: str) -> Fetched | None:
        await self._check_budget()
        try:
            rendered = await self.source.render(url)
        except ProviderUnavailable:
            return None
        except ProviderError:
            return None  # keep the static HTML; the page outcome still records what we have
        if rendered is not None:
            self._count_bytes(len(rendered.result.body))
        return rendered

    # --- shared plumbing ------------------------------------------------------------------

    async def _get(self, url: str, *, content_types: frozenset[str] | None = None) -> Fetched:
        await self._check_budget()
        async with self._spacing:  # polite spacing between request starts
            wait = self._last_request + self._interval - self.clock()
            if wait > 0:
                await self.sleep(wait)
            self._last_request = self.clock()
        fetched = await self.source.fetch(url, content_types=content_types)
        if not fetched.from_cache:
            self._count_bytes(len(fetched.result.body))
        return fetched

    def _count_bytes(self, size: int) -> None:
        assert self._report is not None
        self._report.bytes_fetched += size

    async def _check_budget(self) -> None:
        assert self._report is not None
        if self.is_cancelled is not None and await self.is_cancelled():
            raise CrawlCancelled()
        if self.clock() - self._started > self.limits.wall_clock_seconds:
            raise _Stop("wall_clock")
        if self._report.bytes_fetched >= self.limits.max_total_bytes:
            raise _Stop("total_bytes")

    async def _progress(self, done: int, total: int) -> None:
        if self.on_progress is not None:
            await self.on_progress(done, total)


# --- pure helpers (unit-tested directly) -------------------------------------------------


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """(absolute URL, link text) for every <a href> on the page, in document order."""
    tree = HTMLParser(html)
    base = base_url
    base_node = tree.css_first("base[href]")
    if base_node is not None:
        base = normalise_url(base_node.attributes.get("href") or "", base_url) or base_url
    links: list[tuple[str, str]] = []
    for node in tree.css("a[href]"):
        href = node.attributes.get("href") or ""
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = normalise_url(href, base)
        if url:
            links.append((url, (node.text(strip=True) or "")[:120]))
    return links


def categorise(url: str, text: str = "") -> str | None:
    """Match whole words of the path and link text. Words of 5+ letters also match as
    prefixes ("enquir" -> "enquiry"), so "app" never matches "happy" or "apply"."""
    words = re.findall(r"[a-z0-9]+", f"{urlsplit(url).path} {text}".lower())
    joined = "-".join(words)
    for category, keywords in CATEGORIES:
        for keyword in keywords:
            if "-" in keyword:
                if f"-{keyword}" in f"-{joined}":
                    return category
            elif any(w == keyword or (len(keyword) >= 5 and w.startswith(keyword)) for w in words):
                return category
    return None


def select_pages(
    links: list[tuple[str, str]],
    sitemap_urls: list[str],
    *,
    site: str,
    exclude: set[str],
    limit: int,
) -> list[tuple[str, str, str]]:
    """The high-value pages to fetch: (url, discovered_via, category), best first.
    Links from the homepage beat sitemap entries; shallow paths beat deep ones."""
    candidates: dict[str, tuple[int, int, int, str, str]] = {}
    order = 0
    for via, entries in (("link", links), ("sitemap", [(u, "") for u in sitemap_urls])):
        for url, text in entries:
            order += 1
            if url in exclude or url in candidates or not same_site(url, site):
                continue
            path = urlsplit(url).path.lower()
            if path.endswith(ASSET_SUFFIXES):
                continue
            category = categorise(url, text)
            if category is None:
                continue
            rank = next(i for i, (c, _) in enumerate(CATEGORIES) if c == category)
            depth = len([p for p in path.split("/") if p])
            candidates[url] = (rank, depth, order, via, category)
    chosen: list[tuple[str, str, str]] = []
    per_category: dict[str, int] = {}
    for url, (_, _, _, via, category) in sorted(candidates.items(), key=lambda kv: kv[1][:3]):
        if per_category.get(category, 0) >= MAX_PER_CATEGORY:
            continue
        per_category[category] = per_category.get(category, 0) + 1
        chosen.append((url, via, category))
        if len(chosen) >= limit:
            break
    return chosen


def parse_sitemap(text: str) -> tuple[list[str], list[str]]:
    """(child sitemaps, page URLs) from a sitemap or sitemap index. Tolerant of bad XML."""
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text, flags=re.IGNORECASE)
    urls = [u for u in (normalise_url(_unescape(loc)) for loc in locs) if u]
    if re.search(r"<sitemapindex", text, flags=re.IGNORECASE):
        return urls, []
    return [], urls


def _unescape(value: str) -> str:
    return value.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def page_meta(html: str, url: str) -> tuple[str | None, str | None]:
    tree = HTMLParser(html)
    title_node = tree.css_first("title")
    title = (title_node.text(strip=True) or None) if title_node else None
    canonical_node = tree.css_first('link[rel="canonical"][href]')
    canonical = None
    if canonical_node is not None:
        canonical = normalise_url(canonical_node.attributes.get("href") or "", url)
    return (title[:300] if title else None), canonical


def is_thin(html: str) -> bool:
    """Too little readable text in the static HTML, typically a JavaScript app shell."""
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, template"):
        node.decompose()
    text = tree.body.text(separator=" ", strip=True) if tree.body else ""
    return len(text) < THIN_TEXT_CHARS or bool(APP_ROOT.search(html))
