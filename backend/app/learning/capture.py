"""Recording what was true when a deal was won or lost (master context §13; slice 5.1).

Called in the same transaction as the stage move, so every closed deal has its outcome. Nothing
is estimated: a fact VROS does not have is stored as null (Unknown).
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import Account, Contact
from app.core.enums import ObservationArea, StageOutcome
from app.crm.models import Activity, Lead, Opportunity
from app.deals.models import Deal, Pipeline
from app.evidence.models import Evidence, Observation
from app.learning.models import DealOutcome
from app.research.models import ResearchRun
from app.scoring.models import ScoreSnapshot
from app.similarity.models import SimilarityResult

SCORES = (
    "icp_score",
    "opportunity_score",
    "intent_score",
    "buyer_confidence",
    "data_confidence",
    "service_fit",
    "timing_score",
    "commercial_potential",
    "client_similarity",
    "evidence_strength",
    "priority_score",
)
SIGNAL_WINDOW = timedelta(days=180)
CLOSED = (StageOutcome.WON, StageOutcome.LOST)


def _scores(snap: ScoreSnapshot | None) -> dict[str, Any] | None:
    if snap is None:
        return None
    return {k: None if getattr(snap, k) is None else float(getattr(snap, k)) for k in SCORES}


async def _buyer_role(db: AsyncSession, deal: Deal) -> str | None:
    """The role of the person most logged activities on the deal (or account) were with."""
    for scope in (Activity.deal_id == deal.id, Activity.account_id == deal.account_id):
        row = (
            await db.execute(
                select(Contact.decision_maker_role, func.count())
                .join(Activity, Activity.contact_id == Contact.id)
                .where(scope, Contact.decision_maker_role.is_not(None))
                .group_by(Contact.decision_maker_role)
                .order_by(func.count().desc(), Contact.decision_maker_role)
                .limit(1)
            )
        ).first()
        if row is not None and row[0] is not None:
            return str(row[0].value)
    return None


async def _signals(
    db: AsyncSession, account_id: uuid.UUID, before: datetime
) -> list[dict[str, Any]]:
    when = func.coalesce(Evidence.published_at, Evidence.collected_at)
    rows = await db.execute(
        select(Observation.value, when, Evidence.id)
        .join(ResearchRun, ResearchRun.id == Observation.research_run_id)
        .join(Evidence, Evidence.id == Observation.evidence_id)
        .where(
            ResearchRun.account_id == account_id,
            Observation.area == ObservationArea.SIGNALS,
            when >= before - SIGNAL_WINDOW,
            when <= before,
        )
        .order_by(when.desc())
    )
    seen: set[str] = set()
    out = []
    for value, at, evidence_id in rows.all():
        kind = (value or {}).get("signal")
        if not kind or kind in seen:
            continue
        seen.add(kind)
        out.append({"signal": kind, "at": at.isoformat(), "evidence_id": str(evidence_id)})
    return out


async def capture(db: AsyncSession, deal: Deal, *, late: bool = False) -> DealOutcome:
    """Record the deal's outcome now. Supersedes the deal's current outcome, if it has one."""
    assert deal.outcome in CLOSED, "only won or lost deals have an outcome"
    now = datetime.now(UTC)
    closed_at = deal.closed_at or now
    await supersede(db, deal.id, now)
    account = await db.get(Account, deal.account_id)
    assert account is not None
    pipeline = await db.get(Pipeline, deal.pipeline_id)
    opportunity = await db.get(Opportunity, deal.opportunity_id) if deal.opportunity_id else None
    lead = await db.get(Lead, opportunity.lead_id) if opportunity and opportunity.lead_id else None
    if lead is None:
        lead = (
            await db.execute(
                select(Lead)
                .where(Lead.account_id == account.id, Lead.qualified_at.is_not(None))
                .order_by(Lead.qualified_at)
                .limit(1)
            )
        ).scalar_one_or_none()
    snapshots = select(ScoreSnapshot).where(ScoreSnapshot.account_id == account.id)
    first = (
        await db.execute(snapshots.order_by(ScoreSnapshot.created_at).limit(1))
    ).scalar_one_or_none()
    at_close = (
        await db.execute(
            snapshots.where(ScoreSnapshot.created_at <= closed_at)
            .order_by(ScoreSnapshot.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    reference = (
        await db.execute(
            select(SimilarityResult.reference_project_id)
            .join(ResearchRun, ResearchRun.id == SimilarityResult.research_run_id)
            .where(
                ResearchRun.account_id == account.id,
                SimilarityResult.similarity_score.is_not(None),
            )
            .order_by(ResearchRun.created_at.desc(), SimilarityResult.similarity_score.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    outcome = DealOutcome(
        deal_id=deal.id,
        account_id=account.id,
        outcome=deal.outcome,
        lost_reason=deal.lost_reason if deal.outcome is StageOutcome.LOST else None,
        closed_at=closed_at,
        captured_late=late,
        recorded_at=now,
        pipeline_key=pipeline.key if pipeline else "",
        value=deal.value,
        currency=deal.currency,
        service_id=opportunity.service_id if opportunity else None,
        category_id=opportunity.category_id if opportunity else None,
        industry=account.industry,
        company_size_band=account.company_size_band,
        hq_country=account.hq_country,
        source=(lead.source if lead else None) or account.source,
        buyer_role=await _buyer_role(db, deal),
        deal_days=max(0, (closed_at - deal.created_at).days),
        lead_days=max(0, (closed_at - lead.qualified_at).days)
        if lead and lead.qualified_at
        else None,
        signals=await _signals(db, account.id, closed_at),
        first_scores=_scores(first),
        close_scores=_scores(at_close),
        reference_project_id=reference,
    )
    db.add(outcome)
    await db.flush()
    return outcome


async def supersede(db: AsyncSession, deal_id: uuid.UUID, when: datetime | None = None) -> None:
    """A reopened deal's outcome no longer stands."""
    await db.execute(
        update(DealOutcome)
        .where(DealOutcome.deal_id == deal_id, DealOutcome.superseded_at.is_(None))
        .values(superseded_at=when or datetime.now(UTC))
    )


async def backfill(db: AsyncSession) -> int:
    """Outcomes for won and lost deals that closed before outcomes were recorded."""
    have = select(DealOutcome.deal_id).where(DealOutcome.superseded_at.is_(None))
    deals = (
        await db.execute(
            select(Deal).where(
                Deal.deleted_at.is_(None), Deal.outcome.in_(CLOSED), Deal.id.not_in(have)
            )
        )
    ).scalars()
    count = 0
    for deal in list(deals):
        await capture(db, deal, late=True)
        count += 1
    await db.commit()
    return count
