"""The extract stage: crawled pages -> observations, each backed by an evidence row."""

import hashlib
import uuid
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import PageKind, ResearchStageName
from app.evidence.models import Evidence
from app.evidence.models import Observation as ObservationRow
from app.intelligence.runner import analyse
from app.intelligence.types import Observation, Page, SiteContext
from app.providers.storage import Storage
from app.research.models import RawResponse, ResearchPage, ResearchRun, ResearchStage
from app.research.urls import site_domain


class NothingToAnalyse(Exception):
    pass


async def load_pages(
    db: AsyncSession, run_id: uuid.UUID, storage: Storage
) -> tuple[list[Page], SiteContext]:
    rows = list(
        (
            await db.execute(
                select(ResearchPage, RawResponse)
                .join(RawResponse, RawResponse.id == ResearchPage.raw_response_id)
                .where(ResearchPage.research_run_id == run_id)
                .order_by(ResearchPage.created_at, ResearchPage.id)
            )
        ).all()
    )
    statuses = {
        page.url: page.status_code
        for page in (
            await db.execute(select(ResearchPage).where(ResearchPage.research_run_id == run_id))
        ).scalars()
        if page.kind == PageKind.PAGE
    }
    crawl = (
        await db.execute(
            select(ResearchStage).where(
                ResearchStage.research_run_id == run_id,
                ResearchStage.stage == ResearchStageName.CRAWL,
            )
        )
    ).scalar_one()
    pages: list[Page] = []
    for page, raw in rows:
        usable = (
            page.kind == PageKind.PAGE
            and page.skip_reason is None
            and page.duplicate_of_url is None
            and raw.body_ref is not None
        )
        if not usable:
            continue
        try:
            body = storage.get(raw.body_ref)  # type: ignore[arg-type]
        except (OSError, ValueError):
            continue
        headers = dict(raw.headers)
        if raw.rendered:
            # Rendering keeps no response headers; use the static fetch's for header checks.
            static = (
                await db.execute(
                    select(RawResponse)
                    .where(RawResponse.url == raw.url, RawResponse.rendered.is_(False))
                    .order_by(RawResponse.fetched_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            headers = dict(static.headers) if static else headers
        pages.append(
            Page(
                url=raw.final_url,
                html=body.decode("utf-8", errors="replace"),
                category=page.category,
                headers=headers,
                bytes=raw.bytes,
                rendered=raw.rendered,
            )
        )
    detail = crawl.detail or {}
    home_url = pages[0].url if pages else ""
    ctx = SiteContext(
        home_url=home_url,
        robots=str(detail.get("robots", "missing")),
        sitemaps=tuple(detail.get("sitemaps") or ()),
        statuses=statuses,
    )
    return pages, ctx


async def extract_run(
    run_id: uuid.UUID, sessionmaker: async_sessionmaker[AsyncSession], storage: Storage
) -> dict[str, Any]:
    async with sessionmaker() as db:
        run = await db.get(ResearchRun, run_id)
        assert run is not None
        attempt = run.retry_count
        pages, ctx = await load_pages(db, run_id, storage)
    if not pages:
        raise NothingToAnalyse("No readable pages were crawled.")
    observations, failed = analyse(pages, ctx)
    async with sessionmaker() as db:
        for observation in observations:
            _persist(db, run_id, attempt, observation)
        await db.commit()
    by_area = Counter(o.area.value for o in observations)
    return {
        "pages_analysed": len(pages),
        "observations": len(observations),
        "by_area": dict(sorted(by_area.items())),
        "failed_extractors": failed,
    }


def _persist(db: AsyncSession, run_id: uuid.UUID, attempt: int, item: Observation) -> None:
    now = datetime.now(UTC)
    evidence = Evidence(
        research_run_id=run_id,
        source_url=item.source_url,
        source_domain=site_domain(urlsplit(item.source_url).hostname or ""),
        collected_at=now,
        evidence_type=item.evidence_type,
        evidence_text=item.excerpt,
        content_hash=hashlib.sha256(item.excerpt.encode()).hexdigest(),
        confidence=Decimal(str(round(item.confidence, 2))),
    )
    db.add(evidence)
    db.add(
        ObservationRow(
            research_run_id=run_id,
            attempt=attempt,
            area=item.area,
            key=item.key,
            value=item.value,
            evidence=evidence,
            seen_on=item.seen_on,
            confidence=Decimal(str(round(item.confidence, 2))),
        )
    )
