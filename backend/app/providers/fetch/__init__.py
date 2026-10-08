"""Builds the fetcher and renderer from settings, so callers never wire budgets by hand."""

from app.config import Settings
from app.providers.fetch.netguard import parse_networks
from app.providers.fetch.render import PlaywrightRenderer
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.fetch.types import FetchBudget


def build_fetcher(settings: Settings) -> SafeHttpFetcher:
    return SafeHttpFetcher(
        user_agent=settings.crawler_user_agent,
        budget=FetchBudget(
            max_bytes=settings.crawl_max_bytes_per_response,
            max_redirects=settings.crawl_max_redirects,
            timeout_seconds=settings.crawl_request_timeout_seconds,
            allowed_ports=frozenset(settings.crawl_allowed_ports),
        ),
        allowlist=parse_networks(settings.fetch_private_allowlist),
    )


def build_renderer(settings: Settings, fetcher: SafeHttpFetcher) -> PlaywrightRenderer | None:
    if not settings.render_enabled:
        return None
    return PlaywrightRenderer(
        fetcher,
        executable=settings.chromium_executable,
        timeout_seconds=max(settings.crawl_request_timeout_seconds * 2, 30.0),
    )
