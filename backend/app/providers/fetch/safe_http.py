"""The only way VROS fetches a URL (SECURITY.md §3, PROVIDER_SPEC.md §4).

* Every hop (first request and each redirect) passes the network guard.
* The connection goes to the IP the guard approved; TLS still verifies the real hostname
  (SNI + certificate check), so pinning never weakens HTTPS.
* Redirects are followed by hand, capped, and re-checked.
* The body is streamed and cut off at the byte budget, counted after decompression.
* Unexpected content types are refused. Environment proxies are ignored, so nothing can
  route around the pinning.
"""

import asyncio
import time
from urllib.parse import urljoin

import httpx

from app.providers.fetch.netguard import IPNetwork, Resolver, SystemResolver, resolve_target
from app.providers.fetch.types import FetchBlocked, FetchBudget, FetchFailed, FetchResult

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class SafeHttpFetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        budget: FetchBudget | None = None,
        resolver: Resolver | None = None,
        allowlist: tuple[IPNetwork, ...] = (),
        transport: httpx.AsyncBaseTransport | None = None,
        verify: bool | str | object = True,
    ) -> None:
        self.user_agent = user_agent
        self.budget = budget or FetchBudget()
        self.resolver = resolver or SystemResolver()
        self.allowlist = allowlist
        self._client = httpx.AsyncClient(
            transport=transport,
            verify=verify,  # type: ignore[arg-type]
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(self.budget.timeout_seconds),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "SafeHttpFetcher":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        content_types: frozenset[str] | None = None,
    ) -> FetchResult:
        allowed_types = content_types or self.budget.content_types
        started = time.monotonic()
        redirects: list[str] = []
        current = url
        while True:
            try:
                # Hard cap per hop: a server dripping bytes slowly cannot hold a worker.
                async with asyncio.timeout(self.budget.timeout_seconds):
                    response_headers, status, body, final = await self._one_hop(
                        current, method=method, headers=headers or {}, allowed_types=allowed_types
                    )
            except TimeoutError as exc:
                raise FetchFailed(f"Timed out fetching {current}", code="timeout") from exc
            if status in REDIRECT_STATUSES and "location" in response_headers:
                if len(redirects) >= self.budget.max_redirects:
                    raise FetchBlocked(
                        f"More than {self.budget.max_redirects} redirects.",
                        code="too_many_redirects",
                    )
                current = urljoin(final, response_headers["location"])
                redirects.append(current)
                if status == 303:
                    method = "GET"
                continue
            return FetchResult(
                url=url,
                final_url=final,
                status=status,
                headers=response_headers,
                content_type=_media_type(response_headers.get("content-type")),
                body=body,
                redirects=redirects,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )

    async def _one_hop(
        self, url: str, *, method: str, headers: dict[str, str], allowed_types: frozenset[str]
    ) -> tuple[dict[str, str], int, bytes, str]:
        target = await resolve_target(
            url,
            resolver=self.resolver,
            allowed_ports=self.budget.allowed_ports,
            allowlist=self.allowlist,
        )
        request = self._client.build_request(
            method,
            target.ip_url,
            headers={
                **headers,
                "Host": target.host_header,
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
            },
            extensions={"sni_hostname": target.host},
        )
        logical_url = target.url._replace(fragment="").geturl()
        try:
            response = await self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise FetchFailed(f"Timed out fetching {logical_url}", code="timeout") from exc
        except httpx.HTTPError as exc:
            raise FetchFailed(f"Could not fetch {logical_url}: {type(exc).__name__}") from exc
        try:
            response_headers = {k.lower(): v for k, v in response.headers.items()}
            status = response.status_code
            if status in REDIRECT_STATUSES or status >= 400 or method == "HEAD":
                # Error pages are not content: report the status, never download the body.
                return response_headers, status, b"", logical_url
            media_type = _media_type(response_headers.get("content-type"))
            if media_type not in allowed_types:
                raise FetchBlocked(
                    f"Content type {media_type or 'unknown'} is not accepted.",
                    code="bad_content_type",
                )
            declared = response_headers.get("content-length", "")
            if declared.isdigit() and int(declared) > self.budget.max_bytes:
                raise FetchBlocked("Response is larger than the budget.", code="too_large")
            chunks: list[bytes] = []
            size = 0
            try:
                async for chunk in response.aiter_bytes():  # decoded: counts decompressed bytes
                    size += len(chunk)
                    if size > self.budget.max_bytes:
                        raise FetchBlocked("Response is larger than the budget.", code="too_large")
                    chunks.append(chunk)
            except httpx.TimeoutException as exc:
                raise FetchFailed(f"Timed out reading {logical_url}", code="timeout") from exc
            except httpx.HTTPError as exc:
                raise FetchFailed(f"Could not read {logical_url}: {type(exc).__name__}") from exc
            return response_headers, status, b"".join(chunks), logical_url
        finally:
            await response.aclose()


def _media_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return content_type.split(";", 1)[0].strip().lower() or None
