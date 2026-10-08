"""PageSource backed by the safe fetcher, the renderer, the raw-response cache and storage."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.providers.errors import ProviderUnavailable
from app.providers.fetch.render import PlaywrightRenderer
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.fetch.types import FetchResult
from app.providers.storage import Storage
from app.research.crawler import Fetched
from app.research.models import RawResponse

# Never keep other sites' cookies: they can be session tokens.
DROPPED_HEADERS = frozenset({"set-cookie", "set-cookie2"})


class CachedPageSource:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        storage: Storage,
        fetcher: SafeHttpFetcher,
        renderer: PlaywrightRenderer | None,
        cache_days: int,
        force_refresh: bool = False,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.storage = storage
        self.fetcher = fetcher
        self.renderer = renderer
        self.cache_days = cache_days
        self.force_refresh = force_refresh

    async def fetch(self, url: str, *, content_types: frozenset[str] | None = None) -> Fetched:
        allowed = content_types or self.fetcher.budget.content_types
        cached = await self._cached(url, rendered=False)
        if cached is not None and cached.result.content_type in allowed:
            return cached
        result = await self.fetcher.fetch(url, content_types=content_types)
        return await self._store(result, rendered=False)

    async def render(self, url: str) -> Fetched | None:
        if self.renderer is None:
            return None
        cached = await self._cached(url, rendered=True)
        if cached is not None:
            return cached
        try:
            rendered = await self.renderer.render(url)
        except ProviderUnavailable:
            self.renderer = None  # e.g. Chromium missing: stop trying for this run
            raise
        result = FetchResult(
            url=url,
            final_url=rendered.final_url,
            status=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content_type="text/html",
            body=rendered.html.encode("utf-8"),
        )
        return await self._store(result, rendered=True)

    async def _cached(self, url: str, *, rendered: bool) -> Fetched | None:
        if self.force_refresh or self.cache_days <= 0:
            return None
        since = datetime.now(UTC) - timedelta(days=self.cache_days)
        async with self.sessionmaker() as db:
            row = (
                await db.execute(
                    select(RawResponse)
                    .where(
                        RawResponse.url == url,
                        RawResponse.rendered.is_(rendered),
                        RawResponse.status_code == 200,
                        RawResponse.fetched_at >= since,
                        RawResponse.body_ref.is_not(None),
                    )
                    .order_by(RawResponse.fetched_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if row is None or row.body_ref is None:
            return None
        try:
            body = self.storage.get(row.body_ref)
        except (OSError, ValueError):
            return None  # storage lost the file: fetch again
        result = FetchResult(
            url=url,
            final_url=row.final_url,
            status=row.status_code,
            headers=dict(row.headers),
            content_type=row.content_type,
            body=body,
        )
        return Fetched(result=result, from_cache=True, raw_response_id=str(row.id))

    async def _store(self, result: FetchResult, *, rendered: bool) -> Fetched:
        body_ref = self.storage.put(result.body)
        values = {
            "id": uuid.uuid4(),
            "url": result.url,
            "final_url": result.final_url,
            "rendered": rendered,
            "status_code": result.status,
            "headers": {k: v for k, v in result.headers.items() if k not in DROPPED_HEADERS},
            "body_ref": body_ref,
            "content_type": result.content_type,
            "bytes": len(result.body),
            "content_hash": hashlib.sha256(result.body).hexdigest(),
            "fetched_at": datetime.now(UTC),
        }
        statement = (
            insert(RawResponse)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_raw_responses_url_rendered_content_hash",
                set_={"fetched_at": values["fetched_at"], "final_url": result.final_url},
            )
            .returning(RawResponse.id)
        )
        async with self.sessionmaker() as db:
            raw_id = (await db.execute(statement)).scalar_one()
            await db.commit()
        return Fetched(result=result, from_cache=False, raw_response_id=str(raw_id))
