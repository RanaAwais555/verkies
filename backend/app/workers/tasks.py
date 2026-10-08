"""Worker tasks."""

import asyncio
import contextlib
import logging
import uuid

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
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
