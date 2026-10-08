import pytest

from app.core.enums import PageKind
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.fetch.types import FetchBlocked, FetchResult
from app.research.crawler import (
    CrawlCancelled,
    Crawler,
    CrawlLimits,
    Fetched,
    PageOutcome,
    is_thin,
    parse_sitemap,
    select_pages,
)

SITE = "https://acme.test"
LONG_TEXT = "Acme builds software for logistics teams. " * 20


def html(body: str, *, title: str = "Acme", head: str = "") -> str:
    head_html = f"<head><title>{title}</title>{head}</head>"
    return f"<html>{head_html}<body>{body}<p>{LONG_TEXT}</p></body></html>"


HOME = html(
    '<a href="/about-us">About</a><a href="/services">Services</a>'
    '<a href="/pricing">Pricing</a><a href="/contact">Contact</a>'
    '<a href="/careers">Careers</a><a href="/blog/post-1">Blog</a><a href="/blog/post-2">B</a>'
    '<a href="/blog/post-3">B</a><a href="/random-page">Random</a>'
    '<a href="https://other.test/about">External</a><a href="/brochure.pdf">PDF</a>'
    '<a href="mailto:hi@acme.test">Mail</a>'
)


class FakeSource:
    def __init__(
        self, pages: dict[str, tuple[int, str, str]], renders: dict[str, str] | None = None
    ):
        self.pages = pages  # url -> (status, content type, body)
        self.renders = renders or {}
        self.fetched: list[str] = []
        self.rendered: list[str] = []
        self.render_available = True

    async def fetch(self, url: str, *, content_types: frozenset[str] | None = None) -> Fetched:
        self.fetched.append(url)
        if url not in self.pages:
            return _fetched(url, 404, "text/html", "not found")
        status, kind, body = self.pages[url]
        if status == -1:
            raise FetchBlocked("blocked", code="non_public_address")
        return _fetched(url, status, kind, body)

    async def render(self, url: str) -> Fetched | None:
        if not self.render_available:
            raise ProviderUnavailable("no chromium")
        self.rendered.append(url)
        return _fetched(url, 200, "text/html", self.renders.get(url, html("rendered")))


def _fetched(url: str, status: int, kind: str, body: str) -> Fetched:
    return Fetched(
        FetchResult(
            url=url,
            final_url=url,
            status=status,
            headers={"content-type": kind},
            content_type=kind,
            body=body.encode(),
        )
    )


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


async def crawl(
    source: FakeSource,
    limits: CrawlLimits | None = None,
    cancelled: bool = False,
    clock: Clock | None = None,
) -> tuple[list[PageOutcome], object]:
    outcomes: list[PageOutcome] = []
    clock = clock or Clock()

    async def on_page(outcome: PageOutcome) -> None:
        outcomes.append(outcome)

    async def is_cancelled() -> bool:
        return cancelled

    crawler = Crawler(
        source,
        limits or CrawlLimits(min_interval_seconds=0),
        on_page=on_page,
        is_cancelled=is_cancelled,
        clock=clock,
        sleep=clock.sleep,
    )
    report = await crawler.crawl(f"{SITE}/")
    return outcomes, report


def site(**extra: tuple[int, str, str]) -> FakeSource:
    pages = {
        f"{SITE}/robots.txt": (404, "text/plain", ""),
        f"{SITE}/": (200, "text/html", HOME),
        **{
            f"{SITE}{p}": (200, "text/html", html(p, title=p))
            for p in (
                "/about-us",
                "/services",
                "/pricing",
                "/contact",
                "/careers",
                "/blog/post-1",
                "/blog/post-2",
            )
        },
    }
    pages.update(extra)
    return FakeSource(pages)


async def test_crawls_homepage_then_high_value_same_site_pages() -> None:
    source = site()
    outcomes, report = await crawl(source)
    pages = [o for o in outcomes if o.kind == PageKind.PAGE]
    urls = {o.url for o in pages}
    assert f"{SITE}/" in urls and f"{SITE}/about-us" in urls and f"{SITE}/pricing" in urls
    assert "https://other.test/about" not in source.fetched  # other sites never fetched
    assert f"{SITE}/brochure.pdf" not in source.fetched  # assets skipped
    assert f"{SITE}/random-page" not in source.fetched  # not high value
    assert sum(1 for u in urls if "/blog/" in u) == 2  # at most two per category
    assert report.pages_fetched == len([o for o in pages if o.skip_reason is None])
    assert report.robots == "missing"


async def test_max_pages_is_respected() -> None:
    _, report = await crawl(site(), CrawlLimits(max_pages=3, min_interval_seconds=0))
    assert report.pages_fetched == 3


async def test_robots_disallow_is_obeyed() -> None:
    source = site(
        **{f"{SITE}/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /pricing")}
    )
    outcomes, report = await crawl(source)
    assert f"{SITE}/pricing" not in source.fetched
    skipped = [o for o in outcomes if o.url == f"{SITE}/pricing"]
    assert skipped and skipped[0].skip_reason == "robots_disallowed"
    assert report.robots == "parsed"


async def test_robots_disallowing_everything_stops_before_the_homepage() -> None:
    source = site(**{f"{SITE}/robots.txt": (200, "text/plain", "User-agent: VROSBot\nDisallow: /")})
    _, report = await crawl(source)
    assert source.fetched == [f"{SITE}/robots.txt"]
    assert report.stopped_reason == "robots_disallowed_homepage"


async def test_robots_server_error_means_do_not_crawl() -> None:
    source = site(**{f"{SITE}/robots.txt": (503, "text/plain", "")})
    _, report = await crawl(source)
    assert source.fetched == [f"{SITE}/robots.txt"]
    assert report.robots == "unreachable"


async def test_crawl_delay_spaces_requests() -> None:
    source = site(**{f"{SITE}/robots.txt": (200, "text/plain", "User-agent: *\nCrawl-delay: 3")})
    clock = Clock()
    await crawl(
        source, CrawlLimits(max_pages=3, min_interval_seconds=1, concurrency=1), clock=clock
    )
    assert clock.sleeps and all(s == 3.0 for s in clock.sleeps)


async def test_sitemap_index_is_followed_for_page_candidates() -> None:
    index = f"<sitemapindex><sitemap><loc>{SITE}/sitemap-pages.xml</loc></sitemap></sitemapindex>"
    child = f"<urlset><url><loc>{SITE}/team</loc></url><url><loc>{SITE}/x/deep</loc></url></urlset>"
    source = site(
        **{
            f"{SITE}/sitemap.xml": (200, "application/xml", index),
            f"{SITE}/sitemap-pages.xml": (200, "application/xml", child),
            f"{SITE}/team": (200, "text/html", html("team")),
        }
    )
    outcomes, report = await crawl(source)
    assert f"{SITE}/team" in source.fetched
    team = next(o for o in outcomes if o.url == f"{SITE}/team")
    assert team.discovered_via == "sitemap" and team.category == "team"
    assert report.sitemaps == [f"{SITE}/sitemap.xml", f"{SITE}/sitemap-pages.xml"]


async def test_thin_pages_are_rendered() -> None:
    shell = '<html><head><title>App</title></head><body><div id="root"></div></body></html>'
    source = site(**{f"{SITE}/pricing": (200, "text/html", shell)})
    outcomes, _ = await crawl(source)
    assert source.rendered == [f"{SITE}/pricing"]
    assert next(o for o in outcomes if o.url == f"{SITE}/pricing").rendered


async def test_missing_renderer_keeps_static_html() -> None:
    shell = '<html><head><title>App</title></head><body><div id="root"></div></body></html>'
    source = site(**{f"{SITE}/pricing": (200, "text/html", shell)})
    source.render_available = False
    outcomes, _ = await crawl(source)
    pricing = next(o for o in outcomes if o.url == f"{SITE}/pricing")
    assert not pricing.rendered and pricing.skip_reason is None


async def test_canonical_duplicates_are_marked_not_counted() -> None:
    dup = html("same", head=f'<link rel="canonical" href="{SITE}/services">')
    source = site(**{f"{SITE}/pricing": (200, "text/html", dup)})
    outcomes, report = await crawl(source)
    pricing = next(o for o in outcomes if o.url == f"{SITE}/pricing")
    services = next(o for o in outcomes if o.url == f"{SITE}/services")
    first, second = sorted([pricing, services], key=lambda o: outcomes.index(o))
    assert second.duplicate_of_url == first.url
    assert report.pages_fetched == len(
        [
            o
            for o in outcomes
            if o.kind == PageKind.PAGE and o.skip_reason is None and o.duplicate_of_url is None
        ]
    )


async def test_rate_limited_site_stops_the_crawl() -> None:
    source = site(**{f"{SITE}/about-us": (429, "text/html", "slow down")})
    _, report = await crawl(source, CrawlLimits(min_interval_seconds=0, concurrency=1))
    assert report.stopped_reason == "site_refused_429"
    assert "site_refused_429" in report.limits_hit


async def test_blocked_pages_are_recorded_and_crawl_continues() -> None:
    source = site(**{f"{SITE}/about-us": (-1, "", "")})
    outcomes, report = await crawl(source)
    about = next(o for o in outcomes if o.url == f"{SITE}/about-us")
    assert about.skip_reason == "fetch_failed:non_public_address"
    assert report.pages_fetched > 1


async def test_wall_clock_limit_stops_the_crawl() -> None:
    clock = Clock()
    source = site(**{f"{SITE}/robots.txt": (200, "text/plain", "User-agent: *\nCrawl-delay: 10")})
    _, report = await crawl(
        source,
        CrawlLimits(wall_clock_seconds=25, min_interval_seconds=0, concurrency=1),
        clock=clock,
    )
    assert report.stopped_reason == "wall_clock"


async def test_total_bytes_limit_stops_the_crawl() -> None:
    _, report = await crawl(site(), CrawlLimits(max_total_bytes=2000, min_interval_seconds=0))
    assert report.stopped_reason == "total_bytes"


async def test_cancellation_stops_immediately() -> None:
    with pytest.raises(CrawlCancelled):
        await crawl(site(), cancelled=True)


async def test_unreachable_homepage_ends_with_reason() -> None:
    source = site(**{f"{SITE}/": (-1, "", "")})
    outcomes, report = await crawl(source)
    assert report.pages_fetched == 0
    assert report.stopped_reason == "homepage_unavailable"
    assert outcomes[-1].error


def test_select_pages_prefers_links_and_shallow_paths() -> None:
    links = [(f"{SITE}/company/about/history", "About"), (f"{SITE}/about", "About us")]
    chosen = select_pages(links, [f"{SITE}/team"], site="acme.test", exclude=set(), limit=5)
    assert [c[0] for c in chosen] == [
        f"{SITE}/about",
        f"{SITE}/company/about/history",
        f"{SITE}/team",
    ]


def test_parse_sitemap_tolerates_entities_and_bad_xml() -> None:
    children, pages = parse_sitemap(f"<urlset><url><loc> {SITE}/a?x=1&amp;y=2 </loc></url><broken")
    assert children == [] and pages == [f"{SITE}/a?x=1&y=2"]


@pytest.mark.parametrize(
    ("page", "thin"),
    [
        (html("<h1>Real content</h1>"), False),
        ("<html><body><div id='root'></div><script>app()</script></body></html>", True),
        ("<html><body><p>Hi</p></body></html>", True),
    ],
)
def test_is_thin(page: str, thin: bool) -> None:
    assert is_thin(page) is thin


async def test_provider_errors_from_render_do_not_break_the_page() -> None:
    class Failing(FakeSource):
        async def render(self, url: str) -> Fetched | None:
            raise ProviderError("timeout", code="render_timeout")

    shell = '<html><head><title>App</title></head><body><div id="root"></div></body></html>'
    source = Failing(site(**{f"{SITE}/pricing": (200, "text/html", shell)}).pages)
    outcomes, _ = await crawl(source)
    assert next(o for o in outcomes if o.url == f"{SITE}/pricing").skip_reason is None
