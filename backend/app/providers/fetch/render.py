"""JavaScript rendering with headless Chromium, without giving Chromium network access.

Every request the page makes is intercepted and either refused or fetched by the
SafeHttpFetcher (same SSRF guard, pinning and budgets), then handed back to Chromium.
Chromium is also pointed at a dead proxy, so anything that slipped past interception would
fail rather than reach the network. Downloads, service workers, WebSockets and non-GET
requests are blocked; images, media and fonts are skipped (not needed to read a page).
"""

import asyncio
import contextlib
import logging
import re
from dataclasses import dataclass, field
from html import escape
from typing import TYPE_CHECKING

from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.fetch.types import HTML_TYPES

if TYPE_CHECKING:
    from playwright.async_api import Route, WebSocketRoute

logger = logging.getLogger(__name__)

SKIPPED_RESOURCE_TYPES = frozenset({"image", "media", "font", "imageset", "texttrack"})
SUBRESOURCE_TYPES = HTML_TYPES | frozenset(
    {
        "text/javascript",
        "application/javascript",
        "application/x-javascript",
        "text/css",
        "application/json",
        "text/plain",
        "application/xml",
        "text/xml",
    }
)
DEAD_PROXY = "http://127.0.0.1:9"  # discard port: nothing listens there
CHROMIUM_ARGS = [
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-sync",
    "--dns-prefetch-disable",
    "--no-pings",
    "--disable-dev-shm-usage",
]


@dataclass
class RenderResult:
    url: str
    final_url: str
    html: str
    subrequests: int
    blocked: list[str] = field(default_factory=list)


class PlaywrightRenderer:
    def __init__(
        self,
        fetcher: SafeHttpFetcher,
        *,
        executable: str | None = None,
        timeout_seconds: float = 30.0,
        max_subrequests: int = 60,
        max_total_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        self.fetcher = fetcher
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.max_subrequests = max_subrequests
        self.max_total_bytes = max_total_bytes

    async def render(self, url: str) -> RenderResult:
        try:  # imported here: only the worker image installs Playwright
            from playwright.async_api import Error as PlaywrightError
        except ImportError as exc:
            raise ProviderUnavailable("Playwright is not installed.") from exc
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await self._render(url)
        except TimeoutError as exc:
            raise ProviderError(f"Rendering timed out for {url}", code="render_timeout") from exc
        except PlaywrightError as exc:
            if "Executable doesn't exist" in str(exc):
                raise ProviderUnavailable("Chromium is not installed.") from exc
            raise ProviderError(f"Rendering failed for {url}: {exc.message}") from exc

    async def _render(self, url: str) -> RenderResult:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright

        state = _RenderState(final_url=url)

        async def handle(route: "Route") -> None:
            request = route.request
            if (
                request.method not in ("GET", "HEAD")
                or request.resource_type in SKIPPED_RESOURCE_TYPES
                or state.subrequests >= self.max_subrequests
                or state.bytes >= self.max_total_bytes
            ):
                await route.abort("blockedbyclient")
                return
            state.subrequests += 1
            try:
                result = await self.fetcher.fetch(
                    request.url, method=request.method, content_types=SUBRESOURCE_TYPES
                )
            except ProviderError as exc:
                state.blocked.append(f"{request.url}: {exc.code}")
                await route.abort("blockedbyclient")
                return
            state.bytes += len(result.body)
            body = result.body
            if request.is_navigation_request() and request.frame == page.main_frame:
                state.final_url = result.final_url
                if result.redirects and result.is_html:
                    # Chromium does not route the request after a redirect we hand it, so the
                    # final page is served here directly; <base> keeps relative links right.
                    body = _with_base(body, result.final_url)
            headers = {"content-type": result.headers.get("content-type", "text/plain")}
            await route.fulfill(status=result.status, headers=headers, body=body)

        async def refuse_socket(ws: "WebSocketRoute") -> None:
            await ws.close(code=1008, reason="blocked")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                executable_path=self.executable,
                headless=True,
                args=CHROMIUM_ARGS,
                proxy={"server": DEAD_PROXY},
            )
            try:
                context = await browser.new_context(
                    user_agent=self.fetcher.user_agent,
                    service_workers="block",
                    accept_downloads=False,
                )
                page = await context.new_page()
                await context.route("**/*", handle)
                await context.route_web_socket("**/*", refuse_socket)
                await page.goto(url, wait_until="load", timeout=self.timeout_seconds * 1000)
                # Some pages poll forever; what has rendered so far is enough.
                with contextlib.suppress(PlaywrightError):
                    await page.wait_for_load_state("networkidle", timeout=3000)
                html = await page.content()
                return RenderResult(
                    url=url,
                    final_url=state.final_url,
                    html=html,
                    subrequests=state.subrequests,
                    blocked=state.blocked,
                )
            finally:
                await browser.close()


def _with_base(html: bytes, base_url: str) -> bytes:
    if re.search(rb"<base\s", html[:4096], re.IGNORECASE):
        return html
    tag = f'<base href="{escape(base_url, quote=True)}">'.encode()
    match = re.search(rb"<head[^>]*>", html[:4096], re.IGNORECASE)
    if match:
        return html[: match.end()] + tag + html[match.end() :]
    return tag + html


@dataclass
class _RenderState:
    final_url: str
    subrequests: int = 0
    bytes: int = 0
    blocked: list[str] = field(default_factory=list)
