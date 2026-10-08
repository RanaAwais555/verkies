"""Research runs: start, list, view, cancel and retry. Callers commit, then enqueue."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import AccountDomain
from app.audit import service as audit
from app.auth.models import User
from app.config import Settings
from app.core.enums import AuditSource, JobStatus
from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.providers.fetch.netguard import parse_url
from app.providers.fetch.types import FetchBlocked
from app.research.models import ResearchPage, ResearchRun, ResearchStage
from app.research.pipeline import PIPELINE_STAGES
from app.research.urls import normalised_domain

ACTIVE = frozenset({JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING})
SEE_ALL_PERMISSION = "accounts.read"


def _now() -> datetime:
    return datetime.now(UTC)


def _can_see(user: User, run: ResearchRun) -> bool:
    return SEE_ALL_PERMISSION in user.permission_keys or run.requested_by_id == user.id


async def start_run(db: AsyncSession, *, user: User, url: str, settings: Settings) -> ResearchRun:
    start_url, domain = normalised_domain(url)
    try:  # cheap checks now, so obvious mistakes fail in the form, not in the worker
        parse_url(start_url, allowed_ports=frozenset(settings.crawl_allowed_ports))
    except FetchBlocked as exc:
        raise ValidationFailed(exc.message) from exc
    active = (
        await db.execute(
            select(ResearchRun.id).where(
                ResearchRun.normalised_domain == domain, ResearchRun.status.in_(ACTIVE)
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        raise Conflict(f"Research on {domain} is already in progress (run {active}).")
    existing = (
        await db.execute(select(AccountDomain.account_id).where(AccountDomain.domain == domain))
    ).scalars()
    run = ResearchRun(
        input_url=start_url,
        normalised_domain=domain,
        requested_by_id=user.id,
        status=JobStatus.QUEUED,
        possible_duplicate_of=[str(a) for a in existing],
        crawl_budget={
            "max_pages": settings.crawl_max_pages,
            "max_total_bytes": settings.crawl_max_total_bytes,
            "wall_clock_seconds": settings.crawl_wall_clock_seconds,
        },
    )
    db.add(run)
    await db.flush()
    for stage in PIPELINE_STAGES:
        db.add(ResearchStage(research_run_id=run.id, stage=stage, status=JobStatus.QUEUED))
    audit.record(
        db,
        action="research.started",
        object_table="research_runs",
        object_id=run.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"url": start_url, "domain": domain},
    )
    return run


async def get_run(db: AsyncSession, *, user: User, run_id: uuid.UUID) -> ResearchRun:
    run = await db.get(ResearchRun, run_id)
    if run is None or not _can_see(user, run):
        raise NotFound("Research run not found.")
    return run


async def stages_of(db: AsyncSession, run_id: uuid.UUID) -> list[ResearchStage]:
    order = {stage: i for i, stage in enumerate(PIPELINE_STAGES)}
    rows = (
        await db.execute(select(ResearchStage).where(ResearchStage.research_run_id == run_id))
    ).scalars()
    return sorted(rows, key=lambda s: order.get(s.stage, len(order)))


async def pages_of(db: AsyncSession, run_id: uuid.UUID) -> list[ResearchPage]:
    return list(
        (
            await db.execute(
                select(ResearchPage)
                .where(ResearchPage.research_run_id == run_id)
                .order_by(ResearchPage.created_at, ResearchPage.id)
            )
        ).scalars()
    )


async def list_runs(db: AsyncSession, *, user: User, limit: int) -> list[ResearchRun]:
    query = select(ResearchRun).order_by(ResearchRun.created_at.desc()).limit(limit)
    if SEE_ALL_PERMISSION not in user.permission_keys:
        query = query.where(ResearchRun.requested_by_id == user.id)
    return list((await db.execute(query)).scalars())


async def cancel_run(db: AsyncSession, *, user: User, run_id: uuid.UUID) -> ResearchRun:
    run = await get_run(db, user=user, run_id=run_id)
    if run.status not in ACTIVE:
        raise Conflict(f"This run is {run.status.value} and cannot be cancelled.")
    run.status = JobStatus.CANCELLED
    run.finished_at = _now()
    audit.record(
        db,
        action="research.cancelled",
        object_table="research_runs",
        object_id=run.id,
        user_id=user.id,
        source=AuditSource.API,
    )
    return run


async def retry_run(db: AsyncSession, *, user: User, run_id: uuid.UUID) -> ResearchRun:
    run = await get_run(db, user=user, run_id=run_id)
    if run.requested_by_id != user.id and SEE_ALL_PERMISSION not in user.permission_keys:
        raise PermissionDenied("Only the person who started this run can retry it.")
    if run.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise Conflict(f"This run is {run.status.value}; only failed or cancelled runs can retry.")
    active = (
        await db.execute(
            select(ResearchRun.id).where(
                ResearchRun.normalised_domain == run.normalised_domain,
                ResearchRun.status.in_(ACTIVE),
                ResearchRun.id != run.id,
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        raise Conflict(f"Research on {run.normalised_domain} is already in progress.")
    run.status = JobStatus.RETRYING
    run.retry_count += 1
    run.error = None
    run.started_at = None
    run.finished_at = None
    await db.execute(delete(ResearchPage).where(ResearchPage.research_run_id == run.id))
    for stage in await stages_of(db, run.id):
        stage.status = JobStatus.QUEUED
        stage.progress_pct = 0
        stage.started_at = stage.finished_at = None
        stage.error = None
        stage.detail = {}
    audit.record(
        db,
        action="research.retried",
        object_table="research_runs",
        object_id=run.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"retry_count": run.retry_count},
    )
    return run


async def mark_enqueue_failed(db: AsyncSession, run: ResearchRun) -> None:
    run.status = JobStatus.FAILED
    run.error = "The job queue is unavailable. Try again in a moment."
    run.finished_at = _now()
