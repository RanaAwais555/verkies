"""Runs one research job through its stages, recording progress as it goes (ARCHITECTURE.md §5).

Only implemented stages are listed in PIPELINE_STAGES; later slices append theirs (extract,
detect, qualify, score, match, brief). A run is never reported as having done work it did not.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.core.enums import JobStatus, ResearchStageName
from app.providers.errors import ProviderError
from app.providers.fetch.netguard import resolve_target
from app.providers.fetch.render import PlaywrightRenderer
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.storage import Storage
from app.research.crawler import CrawlCancelled, Crawler, CrawlLimits, PageOutcome
from app.research.models import ResearchPage, ResearchRun, ResearchStage
from app.research.source import CachedPageSource

logger = logging.getLogger(__name__)

PIPELINE_STAGES: tuple[ResearchStageName, ...] = (
    ResearchStageName.VALIDATE,
    ResearchStageName.CRAWL,
)
STARTABLE = frozenset({JobStatus.QUEUED, JobStatus.RETRYING})
INTERNAL_ERROR = "Something went wrong on our side. The error has been logged; try again."


@dataclass
class PipelineDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    settings: Settings
    fetcher: SafeHttpFetcher
    renderer: PlaywrightRenderer | None
    storage: Storage
    force_refresh: bool = False


class StageFailed(Exception):
    """A stage could not complete for a reason the user should see."""


def _now() -> datetime:
    return datetime.now(UTC)


async def run_research(run_id: uuid.UUID, deps: PipelineDeps) -> None:
    if not await _claim(run_id, deps):
        return
    current: ResearchStageName | None = None
    try:
        current = ResearchStageName.VALIDATE
        await _stage(run_id, current, deps, lambda: _validate(run_id, deps))
        current = ResearchStageName.CRAWL
        await _stage(run_id, current, deps, lambda: _crawl(run_id, deps))
        await _finish(run_id, deps, JobStatus.COMPLETED)
    except CrawlCancelled:
        await _set_stage(run_id, current, deps, status=JobStatus.CANCELLED, finished=True)
        await _finish(run_id, deps, JobStatus.CANCELLED, keep_if_cancelled=True)
    except StageFailed as exc:
        await _set_stage(
            run_id, current, deps, status=JobStatus.FAILED, error=str(exc), finished=True
        )
        await _finish(run_id, deps, JobStatus.FAILED, error=str(exc))
    except Exception:
        logger.exception("research run failed", extra={"run_id": str(run_id)})
        await _set_stage(
            run_id, current, deps, status=JobStatus.FAILED, error=INTERNAL_ERROR, finished=True
        )
        await _finish(run_id, deps, JobStatus.FAILED, error=INTERNAL_ERROR)


async def _claim(run_id: uuid.UUID, deps: PipelineDeps) -> bool:
    """Mark the run running if it is waiting, or if a previous worker died mid-run.
    Duplicate deliveries of the same job are ignored."""
    stale_after = timedelta(seconds=deps.settings.crawl_wall_clock_seconds + 300)
    async with deps.sessionmaker() as db:
        run = await db.get(ResearchRun, run_id, with_for_update=True)
        if run is None:
            return False
        stale = (
            run.status == JobStatus.RUNNING
            and run.started_at is not None
            and _now() - run.started_at > stale_after
        )
        if run.status not in STARTABLE and not stale:
            return False
        run.status = JobStatus.RUNNING
        run.started_at = _now()
        run.finished_at = None
        run.error = None
        await db.commit()
    return True


async def _stage(
    run_id: uuid.UUID,
    stage: ResearchStageName,
    deps: PipelineDeps,
    work: Callable[[], Awaitable[dict[str, Any]]],
) -> None:
    await _set_stage(run_id, stage, deps, status=JobStatus.RUNNING, started=True)
    detail = await work()
    await _set_stage(
        run_id, stage, deps, status=JobStatus.COMPLETED, progress=100, detail=detail, finished=True
    )


async def _set_stage(
    run_id: uuid.UUID,
    stage: ResearchStageName | None,
    deps: PipelineDeps,
    *,
    status: JobStatus | None = None,
    progress: int | None = None,
    detail: dict[str, Any] | None = None,
    error: str | None = None,
    started: bool = False,
    finished: bool = False,
) -> None:
    if stage is None:
        return
    async with deps.sessionmaker() as db:
        row = (
            await db.execute(
                select(ResearchStage).where(
                    ResearchStage.research_run_id == run_id, ResearchStage.stage == stage
                )
            )
        ).scalar_one()
        if status is not None:
            row.status = status
        if progress is not None:
            row.progress_pct = progress
        if detail is not None:
            row.detail = detail
        if error is not None:
            row.error = error
        if started:
            row.started_at = _now()
        if finished:
            row.finished_at = _now()
        await db.commit()


async def _finish(
    run_id: uuid.UUID,
    deps: PipelineDeps,
    status: JobStatus,
    *,
    error: str | None = None,
    keep_if_cancelled: bool = False,
) -> None:
    async with deps.sessionmaker() as db:
        run = await db.get(ResearchRun, run_id, with_for_update=True)
        if run is None:
            return
        if run.status == JobStatus.CANCELLED and not keep_if_cancelled:
            # Cancelled while the last stage was finishing: cancellation wins.
            status = JobStatus.CANCELLED
        run.status = status
        run.error = error
        run.finished_at = _now()
        await db.commit()


async def fail_run(
    run_id: uuid.UUID, sessionmaker: async_sessionmaker[AsyncSession], message: str
) -> None:
    """Mark a run and its unfinished stages failed (used when the worker had to stop it)."""
    async with sessionmaker() as db:
        run = await db.get(ResearchRun, run_id, with_for_update=True)
        if run is None or run.status not in (JobStatus.RUNNING, *STARTABLE):
            return
        run.status, run.error, run.finished_at = JobStatus.FAILED, message, _now()
        stages = (
            await db.execute(select(ResearchStage).where(ResearchStage.research_run_id == run_id))
        ).scalars()
        for stage in stages:
            if stage.status == JobStatus.RUNNING:
                stage.status, stage.error, stage.finished_at = JobStatus.FAILED, message, _now()
        await db.commit()


async def _input_url(run_id: uuid.UUID, deps: PipelineDeps) -> str:
    async with deps.sessionmaker() as db:
        run = await db.get(ResearchRun, run_id)
        assert run is not None
        return run.input_url


async def _validate(run_id: uuid.UUID, deps: PipelineDeps) -> dict[str, Any]:
    url = await _input_url(run_id, deps)
    try:
        target = await resolve_target(
            url,
            resolver=deps.fetcher.resolver,
            allowed_ports=deps.fetcher.budget.allowed_ports,
            allowlist=deps.fetcher.allowlist,
        )
    except ProviderError as exc:
        raise StageFailed(exc.message) from exc
    return {"host": target.host, "port": target.port}


async def _crawl(run_id: uuid.UUID, deps: PipelineDeps) -> dict[str, Any]:
    settings = deps.settings
    url = await _input_url(run_id, deps)
    source = CachedPageSource(
        sessionmaker=deps.sessionmaker,
        storage=deps.storage,
        fetcher=deps.fetcher,
        renderer=deps.renderer,
        cache_days=settings.crawl_cache_days,
        force_refresh=deps.force_refresh,
    )

    async def on_page(outcome: PageOutcome) -> None:
        await _record_page(run_id, outcome, deps)

    async def on_progress(done: int, total: int) -> None:
        await _set_stage(
            run_id, ResearchStageName.CRAWL, deps, progress=min(99, int(done * 100 / max(total, 1)))
        )

    async def is_cancelled() -> bool:
        async with deps.sessionmaker() as db:
            status = (
                await db.execute(select(ResearchRun.status).where(ResearchRun.id == run_id))
            ).scalar_one()
        return status == JobStatus.CANCELLED

    crawler = Crawler(
        source,
        CrawlLimits(
            max_pages=settings.crawl_max_pages,
            max_total_bytes=settings.crawl_max_total_bytes,
            wall_clock_seconds=settings.crawl_wall_clock_seconds,
            min_interval_seconds=settings.crawl_min_interval_seconds,
            concurrency=settings.crawl_concurrency,
        ),
        on_page=on_page,
        on_progress=on_progress,
        is_cancelled=is_cancelled,
    )
    report = await crawler.crawl(url)
    if report.pages_fetched == 0:
        reason = report.stopped_reason or "no pages could be fetched"
        raise StageFailed(f"The website could not be read ({reason.replace('_', ' ')}).")
    return asdict(report)


async def _record_page(run_id: uuid.UUID, outcome: PageOutcome, deps: PipelineDeps) -> None:
    fetched = outcome.fetched
    result = fetched.result if fetched else None
    page = ResearchPage(
        research_run_id=run_id,
        kind=outcome.kind,
        url=outcome.url,
        final_url=result.final_url if result else None,
        discovered_via=outcome.discovered_via,
        category=outcome.category,
        status_code=result.status if result else None,
        content_type=result.content_type if result else None,
        bytes=len(result.body) if result else 0,
        raw_response_id=uuid.UUID(fetched.raw_response_id)
        if fetched and fetched.raw_response_id
        else None,
        from_cache=fetched.from_cache if fetched else False,
        rendered=outcome.rendered,
        title=outcome.title,
        canonical_url=outcome.canonical_url,
        duplicate_of_url=outcome.duplicate_of_url,
        fetched_at=_now() if result else None,
        skip_reason=outcome.skip_reason,
        error=outcome.error,
    )
    async with deps.sessionmaker() as db:
        db.add(page)
        await db.commit()
