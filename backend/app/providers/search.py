"""Search provider interface (PROVIDER_SPEC.md §2-3). Optional: with none configured, web
search discovery is unavailable and everything else works.

SearXNG is self-hosted inside the Docker network and configured by the admin, so it is called
directly like Ollama. The websites it returns are only candidates: researching one still goes
through the SSRF-safe fetcher.
"""

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings
from app.providers.errors import ProviderError, ProviderUnavailable

MAX_PAGES = 3


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    engine: str | None = None


class SearchProvider(Protocol):
    name: str

    async def search(
        self, query: str, *, pages: int = 1, language: str | None = None
    ) -> list[SearchResult]: ...


class NullSearchProvider:
    name = "none"

    async def search(
        self, query: str, *, pages: int = 1, language: str | None = None
    ) -> list[SearchResult]:
        raise ProviderUnavailable(
            "Web search is not set up. An admin can enable SearXNG (see the README)."
        )


class SearxngProvider:
    name = "searxng"

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def search(
        self, query: str, *, pages: int = 1, language: str | None = None
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        async with httpx.AsyncClient(
            transport=self.transport, timeout=self.timeout_seconds, trust_env=False
        ) as client:
            for page in range(1, min(max(pages, 1), MAX_PAGES) + 1):
                params = {"q": query, "format": "json", "pageno": str(page), "safesearch": "1"}
                if language:
                    params["language"] = language
                try:
                    response = await client.get(f"{self.base_url}/search", params=params)
                except httpx.HTTPError as exc:
                    raise ProviderUnavailable(f"SearXNG unreachable: {type(exc).__name__}") from exc
                if response.status_code != 200:
                    raise ProviderError(
                        f"SearXNG returned {response.status_code} (is the JSON format enabled?)",
                        code="search_error",
                    )
                try:
                    items = response.json().get("results", [])
                except ValueError as exc:
                    raise ProviderError(
                        "SearXNG returned invalid JSON.", code="search_error"
                    ) from exc
                found = [
                    SearchResult(
                        title=" ".join(str(i.get("title") or "").split())[:300],
                        url=str(i["url"]),
                        snippet=" ".join(str(i.get("content") or "").split())[:500],
                        engine=i.get("engine"),
                    )
                    for i in items
                    if isinstance(i, dict) and isinstance(i.get("url"), str)
                ]
                if not found:
                    break
                results += found
        return results


def build_search_provider(settings: Settings) -> SearchProvider:
    if settings.search_provider == "searxng":
        return SearxngProvider(
            settings.searxng_url, timeout_seconds=settings.search_timeout_seconds
        )
    return NullSearchProvider()
