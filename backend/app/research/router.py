"""/research-runs: start research on a company URL and follow its progress."""

import logging
import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.auth.deps import AppSettings, DbSession, require_permission
from app.auth.models import User
from app.core.errors import AppError
from app.research import service
from app.research.schemas import (
    Assessment,
    EvidenceOut,
    Intelligence,
    ObservationOut,
    OpportunityOut,
    PageOut,
    QualificationOut,
    RunDetail,
    RunOut,
    ScoreOut,
    StartRun,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research-runs", tags=["research"])

Researcher = Annotated[User, Depends(require_permission("research.run"))]
Viewer = Annotated[
    User, Depends(require_permission("research.run", "accounts.read", "accounts.read_own"))
]


class QueueUnavailable(AppError):
    status_code = 503
    code = "queue_unavailable"


def enqueue_research(run_id: uuid.UUID) -> None:
    from app.workers.celery_app import celery_app

    celery_app.send_task("vros.research.run", args=[str(run_id)])


def get_enqueuer() -> Callable[[uuid.UUID], None]:
    return enqueue_research


Enqueuer = Annotated[Callable[[uuid.UUID], None], Depends(get_enqueuer)]


async def _out(db: DbSession, run_id: uuid.UUID, user: User) -> RunOut:
    run = await service.get_run(db, user=user, run_id=run_id)
    return RunOut.of(run, await service.stages_of(db, run.id))


async def _enqueue_or_fail(db: DbSession, run_id: uuid.UUID, user: User, enqueue: Enqueuer) -> None:
    try:
        enqueue(run_id)
    except Exception as exc:
        logger.exception("could not enqueue research run", extra={"run_id": str(run_id)})
        run = await service.get_run(db, user=user, run_id=run_id)
        await service.mark_enqueue_failed(db, run)
        await db.commit()
        raise QueueUnavailable("The job queue is unavailable. Try again in a moment.") from exc


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start(
    body: StartRun, user: Researcher, db: DbSession, settings: AppSettings, enqueue: Enqueuer
) -> RunOut:
    run = await service.start_run(db, user=user, url=body.url, settings=settings)
    await db.commit()
    await _enqueue_or_fail(db, run.id, user, enqueue)
    return await _out(db, run.id, user)


@router.get("")
async def list_runs(
    user: Viewer, db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 25
) -> list[RunOut]:
    runs = await service.list_runs(db, user=user, limit=limit)
    return [RunOut.of(r, await service.stages_of(db, r.id)) for r in runs]


@router.get("/{run_id}")
async def get(run_id: uuid.UUID, user: Viewer, db: DbSession) -> RunDetail:
    run = await service.get_run(db, user=user, run_id=run_id)
    stages = await service.stages_of(db, run.id)
    pages = await service.pages_of(db, run.id)
    return RunDetail(**RunOut.of(run, stages).model_dump(), pages=[PageOut.of(p) for p in pages])


@router.get("/{run_id}/intelligence")
async def intelligence(run_id: uuid.UUID, user: Viewer, db: DbSession) -> Intelligence:
    run = await service.get_run(db, user=user, run_id=run_id)
    areas: dict[str, list[ObservationOut]] = {}
    for row in await service.observations_of(db, run):
        areas.setdefault(row.area.value, []).append(ObservationOut.of(row))
    return Intelligence(run_id=run.id, attempt=run.retry_count, areas=areas)


def _evidence_out(item: Any) -> EvidenceOut:
    return EvidenceOut(
        id=item.id,
        source_url=item.source_url,
        evidence_type=item.evidence_type.value,
        excerpt=item.evidence_text,
        collected_at=item.collected_at,
        confidence=float(item.confidence),
    )


@router.get("/{run_id}/assessment")
async def assessment(run_id: uuid.UUID, user: Viewer, db: DbSession) -> Assessment:
    run = await service.get_run(db, user=user, run_id=run_id)
    found = await service.assessment_of(db, run)
    q = found["qualification"]
    s = found["snapshot"]
    dims = s.breakdown.get("dimensions", {}) if s else {}
    return Assessment(
        run_id=run.id,
        opportunities=[
            OpportunityOut(
                id=c.id,
                category=key,
                title=c.title,
                problem=c.problem_statement,
                confidence=float(c.confidence),
                rule_key=c.rule_key,
                evidence=[_evidence_out(e) for e in evidence],
            )
            for c, key, evidence in found["candidates"]
        ],
        qualification=QualificationOut(
            icp_fit=None if q.icp_fit is None else float(q.icp_fit),
            hard_reject=q.hard_reject,
            rejection_reason=q.rejection_reason.value if q.rejection_reason else None,
            explanation=q.explanation,
            components=q.components,
            negative_icp_hits=q.negative_icp_hits,
        )
        if q
        else None,
        score=ScoreOut(
            scores={name: entry["score"] for name, entry in dims.items()},
            priority_score=None if s.priority_score is None else float(s.priority_score),
            priority_band=s.priority_band.value if s.priority_band else None,
            qualifies=s.qualifies,
            not_qualified_because=s.breakdown.get("not_qualified_because", []),
            breakdown=s.breakdown,
            created_at=s.created_at,
        )
        if s
        else None,
    )


@router.post("/{run_id}/cancel")
async def cancel(run_id: uuid.UUID, user: Researcher, db: DbSession) -> RunOut:
    await service.cancel_run(db, user=user, run_id=run_id)
    await db.commit()
    return await _out(db, run_id, user)


@router.post("/{run_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry(run_id: uuid.UUID, user: Researcher, db: DbSession, enqueue: Enqueuer) -> RunOut:
    await service.retry_run(db, user=user, run_id=run_id)
    await db.commit()
    await _enqueue_or_fail(db, run_id, user, enqueue)
    return await _out(db, run_id, user)
