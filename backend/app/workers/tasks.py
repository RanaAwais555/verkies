"""Worker tasks."""

import asyncio
import contextlib
import logging
import uuid

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.providers.ai import build_ai_provider
from app.providers.fetch import build_fetcher, build_renderer
from app.providers.storage import LocalStorage
from app.research.pipeline import INTERNAL_ERROR, PipelineDeps, fail_run, run_research
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
_settings = get_settings()


@celery_app.task(name="vros.ping")
def ping() -> str:
    """Round-trip check that a worker is consuming the queue."""
    return "pong"


async def run_research_job(run_id: uuid.UUID) -> None:
    settings = get_settings()
    # A fresh engine per job: each task runs in its own event loop.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    fetcher = build_fetcher(settings)
    try:
        await run_research(
            run_id,
            PipelineDeps(
                sessionmaker=async_sessionmaker(engine, expire_on_commit=False),
                settings=settings,
                fetcher=fetcher,
                renderer=build_renderer(settings, fetcher),
                storage=LocalStorage(settings.storage_dir),
                ai=build_ai_provider(settings),
            ),
        )
    finally:
        await fetcher.aclose()
        await engine.dispose()


@celery_app.task(
    name="vros.research.run",
    soft_time_limit=int(_settings.crawl_wall_clock_seconds) + 120,
    time_limit=int(_settings.crawl_wall_clock_seconds) + 180,
)
def research_run(run_id: str) -> None:
    try:
        asyncio.run(run_research_job(uuid.UUID(run_id)))
    except SoftTimeLimitExceeded:
        # The pipeline's own limits normally stop it first. Never leave the run "running".
        asyncio.run(_fail(uuid.UUID(run_id), "The research took too long and was stopped."))
    except Exception:
        # Anything that escaped the pipeline (e.g. the database was briefly unreachable):
        # record it on the run rather than leaving it queued forever, then let Celery log it.
        logger.exception("research task crashed", extra={"run_id": run_id})
        with contextlib.suppress(Exception):
            asyncio.run(_fail(uuid.UUID(run_id), INTERNAL_ERROR))
        raise


async def _fail(run_id: uuid.UUID, message: str) -> None:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        await fail_run(run_id, async_sessionmaker(engine, expire_on_commit=False), message)
    finally:
        await engine.dispose()


async def find_websites_job(job_id: uuid.UUID) -> None:
    from app.discovery.websites import find_websites
    from app.providers.search import build_search_provider
    from app.research.source import CachedPageSource

    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    fetcher = build_fetcher(settings)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await find_websites(
            job_id,
            sessionmaker,
            build_search_provider(settings),
            CachedPageSource(
                sessionmaker=sessionmaker,
                storage=LocalStorage(settings.storage_dir),
                fetcher=fetcher,
                renderer=None,
                cache_days=settings.crawl_cache_days,
            ),
        )
    finally:
        await fetcher.aclose()
        await engine.dispose()


@celery_app.task(name="vros.discovery.find_websites", soft_time_limit=1800, time_limit=1900)
def discovery_find_websites(job_id: str) -> None:
    asyncio.run(find_websites_job(uuid.UUID(job_id)))
