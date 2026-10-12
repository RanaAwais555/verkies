"""Worker tasks."""

import asyncio
import contextlib
import logging
import uuid

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.clients import health
from app.config import get_settings
from app.monitoring import service as monitoring
from app.providers.ai import build_ai_provider
from app.providers.fetch import build_fetcher, build_renderer
from app.providers.storage import LocalStorage
from app.registry.stage import Registries
from app.research.pipeline import INTERNAL_ERROR, PipelineDeps, fail_run, run_research
from app.research.source import CachedPageSource
from app.signals.jobs import JobBoards
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


async def client_health_job() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            done = await health.sweep(db)
        logger.info(
            "client health checked",
            extra={"assessed": done.assessed, "changed": done.changed, "risks": done.risks_raised},
        )
    finally:
        await engine.dispose()


@celery_app.task(name="vros.clients.health_sweep", soft_time_limit=600, time_limit=660)
def client_health_sweep() -> None:
    """The retention engine's daily run (slice 4.2), scheduled by the worker's beat."""
    asyncio.run(client_health_job())


async def monitoring_job(account_id: uuid.UUID | None, user_id: uuid.UUID | None) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    fetcher = build_fetcher(settings)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    deps = monitoring.MonitorDeps(
        sessionmaker=sessionmaker,
        # Fresh copies every time: a cached feed would never show anything new.
        source=CachedPageSource(
            sessionmaker=sessionmaker,
            storage=LocalStorage(settings.storage_dir),
            fetcher=fetcher,
            renderer=None,
            cache_days=settings.crawl_cache_days,
            force_refresh=True,
        ),
        fetcher=fetcher,
        boards=JobBoards.default(),
        registries=Registries.from_settings(settings),
    )
    try:
        if account_id is None:
            results = await monitoring.check_all(deps)
        else:
            results = [await monitoring.check_account(account_id, deps, requested_by=user_id)]
        logger.info(
            "monitoring checked",
            extra={
                "accounts": len(results),
                "checked": sum(1 for r in results if r.checked),
                "new_signals": sum(r.new for r in results),
            },
        )
    finally:
        await fetcher.aclose()
        await engine.dispose()


@celery_app.task(name="vros.monitoring.check_watched", soft_time_limit=3600, time_limit=3660)
def monitoring_check_watched() -> None:
    """Every watched account, once a day (slice 6.1), scheduled by the worker's beat."""
    asyncio.run(monitoring_job(None, None))


@celery_app.task(name="vros.monitoring.check_account", soft_time_limit=600, time_limit=660)
def monitoring_check_account(account_id: str, user_id: str) -> None:
    asyncio.run(monitoring_job(uuid.UUID(account_id), uuid.UUID(user_id)))
