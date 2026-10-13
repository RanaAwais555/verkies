"""Google Safe Browsing Lookup API v4 (slice 8.2): is the site on Google's list of malware or
phishing sites? A flagged site shows a full-page warning in Chrome and Firefox, which is a
problem the owner needs to hear about.

Optional: needs a Google API key with the Safe Browsing API enabled
(VROS_SAFE_BROWSING_API_KEY). The endpoint is fixed and is Google's, so it is called directly
(like SearXNG and Ollama); no URL from a crawled page is ever requested here. Only the site's
homepage URL is sent.
"""

from typing import Any

import httpx

from app.providers.errors import ProviderError, ProviderUnavailable

API = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
THREATS = ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"]


def request_body(url: str) -> dict[str, Any]:
    return {
        "client": {"clientId": "vros", "clientVersion": "1"},
        "threatInfo": {
            "threatTypes": THREATS,
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }


def parse(data: Any) -> list[str]:
    """The threat types Google lists for the URL; empty when it is not listed."""
    if not isinstance(data, dict):
        raise ProviderError("Safe Browsing returned no result.", code="safe_browsing_bad")
    matches = data.get("matches") or []
    return sorted({str(m.get("threatType")) for m in matches if isinstance(m, dict)})


class SafeBrowsing:
    def __init__(
        self,
        api_key: str | None,
        *,
        url: str = API,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def threats(self, site_url: str) -> list[str]:
        if not self.api_key:
            raise ProviderUnavailable("Safe Browsing needs VROS_SAFE_BROWSING_API_KEY.")
        async with httpx.AsyncClient(
            transport=self.transport, timeout=self.timeout_seconds, trust_env=False
        ) as client:
            try:
                response = await client.post(
                    self.url, params={"key": self.api_key}, json=request_body(site_url)
                )
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(
                    f"Safe Browsing unreachable: {type(exc).__name__}"
                ) from exc
        if response.status_code in (400, 401, 403):
            raise ProviderUnavailable("Google refused the Safe Browsing key.")
        if response.status_code != 200:
            raise ProviderError(
                f"Safe Browsing returned {response.status_code}.", code="safe_browsing"
            )
        try:
            return parse(response.json())
        except ValueError as exc:
            raise ProviderError(
                "Safe Browsing returned invalid JSON.", code="safe_browsing"
            ) from exc
