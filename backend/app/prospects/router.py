"""/prospects: the review queue, and approving or rejecting researched prospects."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError

from app.auth.deps import AppSettings, DbSession, require_permission
from app.auth.models import User
from app.core.errors import Conflict
from app.prospects import service
from app.prospects.schemas import (
    ApprovalOut,
    ApproveBody,
    DuplicateOut,
    QueueItemOut,
    RejectBody,
    RejectionOut,
    scores_of,
)

router = APIRouter(prefix="/prospects", tags=["prospects"])

Reviewer = Annotated[User, Depends(require_permission("prospects.review"))]


@router.get("")
async def review_queue(user: Reviewer, db: DbSession) -> list[QueueItemOut]:
    items = await service.queue(db)
    return [
        QueueItemOut(
            run_id=i.run.id,
            domain=i.run.normalised_domain,
            input_url=i.run.input_url,
            company=i.summary.get("company"),
            priority_score=i.summary.get("priority_score"),
            priority_band=i.summary.get("priority_band"),
            qualifies=bool(i.summary.get("qualifies")),
            hard_reject=i.hard_reject,
            recommended_rejection=i.recommended_rejection.value
            if i.recommended_rejection
            else None,
            explanation=i.explanation,
            next_action=i.next_action,
            scores=scores_of(i.summary),
            possible_duplicates=[
                DuplicateOut.model_validate(d)
                for d in service.describe_duplicates(i.possible_duplicates)
            ],
            requested_by_id=i.run.requested_by_id,
            finished_at=i.run.finished_at,
        )
        for i in items
    ]


@router.post("/{run_id}/approve")
async def approve(
    run_id: uuid.UUID, body: ApproveBody, user: Reviewer, db: DbSession, settings: AppSettings
) -> ApprovalOut:
    try:
        result = await service.approve(
            db,
            user=user,
            run_id=run_id,
            data=service.ApproveInput(**body.model_dump()),
            settings=settings,
        )
        await db.commit()
    except IntegrityError as exc:  # e.g. the same domain approved into a new account meanwhile
        await db.rollback()
        raise Conflict(
            "This prospect changed while you were approving it; reload and try again."
        ) from exc
    return ApprovalOut(
        run_id=run_id,
        account_id=result.account.id,
        created_account=result.created_account,
        lead_id=result.lead.id,
        opportunity_id=result.opportunity.id if result.opportunity else None,
        task_id=result.task.id,
        task_due_at=result.task.due_at,
        contact_ids=[c.id for c in result.contacts],
    )


@router.post("/{run_id}/reject")
async def reject(
    run_id: uuid.UUID, body: RejectBody, user: Reviewer, db: DbSession
) -> RejectionOut:
    run = await service.reject(
        db, user=user, run_id=run_id, reason=body.reason, note=body.note, suppress=body.suppress
    )
    await db.commit()
    return RejectionOut(
        run_id=run.id,
        review_status=run.review_status.value,
        rejection_reason=body.reason.value,
        rejection_note=run.rejection_note,
        suppressed=body.suppress,
    )
