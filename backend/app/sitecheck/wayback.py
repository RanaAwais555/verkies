"""The Internet Archive's Wayback Machine (slice 8.2): when a homepage was first archived and when
its archived content last changed. Keyless; the CDX API is public.

A change in the archive's content digest is any change to the page, a new date or a new phone
number as much as a redesign, so this reports "last archived change", never "last redesign". A
site whose homepage has not changed in years is a strong neglect signal; a recent change says
little.
"""

import json
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from app.providers.errors import ProviderError
from app.providers.fetch.safe_http import SafeHttpFetcher

CDX = "https://web.archive.org/cdx/search/cdx"
PUBLIC_PAGE = "https://web.archive.org/web/*/{domain}"
TYPES = frozenset({"application/json", "text/plain"})
RECENT_VERSIONS = 50


@dataclass(frozen=True)
class ArchiveRecord:
    first_captured: date
    last_changed: date
    recent_versions: int  # distinct homepage versions among the latest captures


def _day(timestamp: str) -> date | None:
    try:
        return date(int(timestamp[:4]), int(timestamp[4:6]), int(timestamp[6:8]))
    except (ValueError, IndexError):
        return None


def _rows(body: bytes) -> list[list[str]]:
    """CDX JSON: a header row, then one row per capture. Empty body: never archived."""
    if not body.strip():
        return []
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise ProviderError(
            "The Wayback Machine returned invalid JSON.", code="archive_bad"
        ) from exc
    if not isinstance(data, list):
        raise ProviderError("The Wayback Machine returned no captures.", code="archive_bad")
    return [r for r in data[1:] if isinstance(r, list) and r]


def parse(first: bytes, recent: bytes) -> ArchiveRecord | None:
    first_rows, recent_rows = _rows(first), _rows(recent)
    if not first_rows or not recent_rows:
        return None
    first_day, last_day = _day(first_rows[0][0]), _day(recent_rows[-1][0])
    if first_day is None or last_day is None:
        return None
    return ArchiveRecord(first_day, last_day, len(recent_rows))


class Wayback:
    def __init__(self, *, enabled: bool = True, base_url: str = CDX) -> None:
        self.enabled = enabled
        self.base_url = base_url

    async def _get(self, fetcher: SafeHttpFetcher, params: dict[str, str]) -> bytes:
        result = await fetcher.fetch(f"{self.base_url}?{urlencode(params)}", content_types=TYPES)
        if result.status != 200:
            raise ProviderError(f"The Wayback Machine returned {result.status}.", code="archive")
        return result.body

    async def lookup(self, fetcher: SafeHttpFetcher, domain: str) -> ArchiveRecord | None:
        """None when the homepage has never been archived."""
        first = await self._get(
            fetcher, {"url": domain, "output": "json", "fl": "timestamp", "limit": "1"}
        )
        recent = await self._get(
            fetcher,
            {
                "url": domain,
                "output": "json",
                "fl": "timestamp,digest",
                "collapse": "digest",
                "filter": "statuscode:200",
                "limit": f"-{RECENT_VERSIONS}",
            },
        )
        return parse(first, recent)
