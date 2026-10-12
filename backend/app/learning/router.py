"""/accounts/{id}/sales-feedback and /deals/{id}/outcome: what the learning engine learns from
(slice 5.1); /learning/win-loss: what won and lost deals have in common (slice 5.2)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.accounts import access
from app.accounts.models import Account
from app.audit import service as audit
from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.catalogue.models import ReferenceProject, Service
from app.core.enums import AuditSource, FeedbackKind
from app.core.errors import NotFound, ValidationFailed
from app.crm import timeline
from app.crm.models import Lead, Opportunity
from app.deals.service import LOST_REASON_LABELS, get_deal
from app.learning import analysis
from app.learning.labels import FEEDBACK_LABELS
from app.learning.models import DealOutcome, SalesFeedback
from app.opportunities.models import OpportunityCategory

router = APIRouter(tags=["learning"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]


class KindOut(BaseModel):
    key: str
    label: str


class SalesFeedbackOut(BaseModel):
    id: uuid.UUID
    kind: str
    label: str
    note: str | None
    lead_id: uuid.UUID | None
    opportunity_id: uuid.UUID | None
    given_by: str | None
    created_at: datetime


class SalesFeedbackIn(BaseModel):
    kind: FeedbackKind
    note: str | None = Field(default=None, max_length=2000)
    lead_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None


class OutcomeOut(BaseModel):
    outcome: str
    lost_reason: str | None
    closed_at: datetime
    captured_late: bool
    pipeline_key: str
    value: float | None
    currency: str
    service: str | None
    opportunity_type: str | None
    industry: str | None
    company_size_band: str | None
    hq_country: str | None
    source: str | None
    buyer_role: str | None
    deal_days: int
    lead_days: int | None
    signals: list[dict[str, Any]]
    first_scores: dict[str, Any] | None
    close_scores: dict[str, Any] | None
    reference_project: str | None


async def _account(db: DbSession, user: User, account_id: uuid.UUID) -> Account:
    account = await db.get(Account, account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")
    return account


def _out(f: SalesFeedback, names: dict[uuid.UUID, str]) -> SalesFeedbackOut:
    return SalesFeedbackOut(
        id=f.id,
        kind=f.kind.value,
        label=FEEDBACK_LABELS[f.kind],
        note=f.note,
        lead_id=f.lead_id,
        opportunity_id=f.opportunity_id,
        given_by=names.get(f.given_by_id) if f.given_by_id else None,
        created_at=f.created_at,
    )


@router.get("/sales-feedback/kinds")
async def feedback_kinds(user: Member) -> list[KindOut]:
    return [KindOut(key=k.value, label=label) for k, label in FEEDBACK_LABELS.items()]


@router.get("/accounts/{account_id}/sales-feedback")
async def list_feedback(
    account_id: uuid.UUID, user: Member, db: DbSession
) -> list[SalesFeedbackOut]:
    account = await _account(db, user, account_id)
    rows = (
        await db.execute(
            select(SalesFeedback, User.name)
            .outerjoin(User, User.id == SalesFeedback.given_by_id)
            .where(SalesFeedback.account_id == account.id)
            .order_by(SalesFeedback.created_at.desc())
            .limit(200)
        )
    ).all()
    return [_out(f, {f.given_by_id: n} if f.given_by_id and n else {}) for f, n in rows]


@router.post("/accounts/{account_id}/sales-feedback", status_code=201)
async def give_feedback(
    account_id: uuid.UUID, body: SalesFeedbackIn, user: Member, db: DbSession
) -> SalesFeedbackOut:
    """§15 feedback. Stored for the learning engine; it changes nothing else by itself."""
    account = await _account(db, user, account_id)
    for model, record_id, what in (
        (Lead, body.lead_id, "lead"),
        (Opportunity, body.opportunity_id, "opportunity"),
    ):
        if record_id is None:
            continue
        found: Any = await db.get(model, record_id)
        if found is None or found.account_id != account.id:
            raise ValidationFailed(f"That {what} is not on this account.")
    feedback = SalesFeedback(
        account_id=account.id,
        lead_id=body.lead_id,
        opportunity_id=body.opportunity_id,
        kind=body.kind,
        note=(body.note or "").strip() or None,
        given_by_id=user.id,
    )
    db.add(feedback)
    await db.flush()
    label = FEEDBACK_LABELS[body.kind]
    timeline.add(
        db,
        account_id=account.id,
        event_type="feedback.given",
        summary=f"Feedback: {label}" + (f". {feedback.note[:200]}" if feedback.note else "."),
        actor_id=user.id,
        ref_table="sales_feedback",
        ref_id=feedback.id,
    )
    audit.record(
        db,
        action="sales_feedback.given",
        object_table="sales_feedback",
        object_id=feedback.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"account_id": str(account.id), "kind": body.kind.value},
    )
    await db.commit()
    await db.refresh(feedback)
    return _out(feedback, {user.id: user.name})


@router.get("/deals/{deal_id}/outcome")
async def deal_outcome(deal_id: uuid.UUID, user: Member, db: DbSession) -> OutcomeOut | None:
    """What was true when the deal was won or lost; null while it is open."""
    view = await get_deal(db, user=user, deal_id=deal_id)
    o = (
        await db.execute(
            select(DealOutcome).where(
                DealOutcome.deal_id == view.deal.id, DealOutcome.superseded_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if o is None:
        return None
    service = await db.get(Service, o.service_id) if o.service_id else None
    category = await db.get(OpportunityCategory, o.category_id) if o.category_id else None
    reference = (
        await db.get(ReferenceProject, o.reference_project_id) if o.reference_project_id else None
    )
    return OutcomeOut(
        outcome=o.outcome.value,
        lost_reason=LOST_REASON_LABELS[o.lost_reason] if o.lost_reason else None,
        closed_at=o.closed_at,
        captured_late=o.captured_late,
        pipeline_key=o.pipeline_key,
        value=float(o.value) if o.value is not None else None,
        currency=o.currency,
        service=service.name if service else None,
        opportunity_type=category.name if category else None,
        industry=o.industry,
        company_size_band=o.company_size_band,
        hq_country=o.hq_country,
        source=o.source,
        buyer_role=o.buyer_role,
        deal_days=o.deal_days,
        lead_days=o.lead_days,
        signals=o.signals,
        first_scores=o.first_scores,
        close_scores=o.close_scores,
        reference_project=reference.name if reference else None,
    )


# --- win/loss analysis (slice 5.2) -------------------------------------------------------------


class MoneyOut(BaseModel):
    amount: float
    currency: str


class GroupOut(BaseModel):
    label: str
    won: int
    lost: int
    total: int
    # None when there are fewer closed deals than the minimum sample: too few to learn from.
    win_rate: float | None
    won_value: list[MoneyOut]
    won_unknown_value: int
    avg_days_to_win: float | None

    @classmethod
    def of(cls, g: analysis.Group, min_sample: int) -> "GroupOut":
        return cls(
            label=g.label,
            won=g.won,
            lost=g.lost,
            total=g.total,
            win_rate=analysis.win_rate(g.won, g.total, min_sample),
            won_value=[
                MoneyOut(amount=float(v), currency=c) for c, v in sorted(g.won_value.items())
            ],
            won_unknown_value=g.won_unknown_value,
            avg_days_to_win=sum(g.won_days) / len(g.won_days) if g.won_days else None,
        )


class DimensionOut(BaseModel):
    key: str
    label: str
    groups: list[GroupOut]


class SignalOut(BaseModel):
    signal: str
    label: str
    with_signal: GroupOut
    without_signal: GroupOut


class ReasonCountOut(BaseModel):
    reason: str
    deals: int


class WinLossOut(BaseModel):
    since: datetime | None
    min_sample: int
    overall: GroupOut
    captured_late: int
    dimensions: list[DimensionOut]
    signals: list[SignalOut]
    lost_reasons: list[ReasonCountOut]
    feedback: list[GroupOut]


@router.get("/learning/win-loss")
async def win_loss(
    user: Member,
    db: DbSession,
    months: Annotated[int, Query(ge=0, le=120)] = 12,
    pipeline: Annotated[str | None, Query(max_length=60)] = None,
) -> WinLossOut:
    """What the deals won and lost (on accounts you can see) have in common, over the last
    `months` (0 for all time)."""
    found = await analysis.analyse(db, user=user, months=months or None, pipeline=pipeline)
    n = found.min_sample
    return WinLossOut(
        since=found.since,
        min_sample=n,
        overall=GroupOut.of(found.overall, n),
        captured_late=found.late,
        dimensions=[
            DimensionOut(key=d.key, label=d.label, groups=[GroupOut.of(g, n) for g in d.groups])
            for d in found.dimensions
        ],
        signals=[
            SignalOut(
                signal=s.signal,
                label=s.label,
                with_signal=GroupOut.of(s.with_signal, n),
                without_signal=GroupOut.of(s.without_signal, n),
            )
            for s in found.signals
        ],
        lost_reasons=[ReasonCountOut(reason=r, deals=c) for r, c in found.lost_reasons],
        feedback=[GroupOut.of(g, n) for g in found.feedback],
    )
