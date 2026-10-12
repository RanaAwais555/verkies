"""Deals in pipelines: open, edit, move, and forecast (master context §12, §13; slice 3.1).

A deal's value is entered by a person and is Unknown until then; nothing here estimates one. The
weighted value is value times probability only when both are known, and the forecast reports how
many deals it could not weigh instead of counting them as zero.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account
from app.audit import service as audit
from app.auth.models import User
from app.clients.models import Project
from app.config import get_settings
from app.core.enums import (
    AccountType,
    AuditSource,
    LostReason,
    PipelineKind,
    StageOutcome,
    TaskStatus,
)
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.crm import timeline
from app.crm.activities import latest_touch
from app.crm.follow_ups import is_quiet, last_touch
from app.crm.models import Opportunity, Task
from app.deals.models import Deal, DealStageChange, Pipeline, PipelineStage

CLOSED = (StageOutcome.WON, StageOutcome.LOST, StageOutcome.INACTIVE)
OPEN_TASK = (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)
LOST_REASON_LABELS = {
    LostReason.PRICE: "Price",
    LostReason.NO_BUDGET: "No budget",
    LostReason.TIMING: "Timing",
    LostReason.COMPETITOR: "Competitor",
    LostReason.INTERNAL_DEVELOPMENT: "Internal development",
    LostReason.FREELANCER: "Freelancer",
    LostReason.ANOTHER_AGENCY: "Another agency",
    LostReason.CANCELLED: "Cancelled",
    LostReason.NO_DECISION: "No decision",
    LostReason.LOST_CONTACT: "Lost contact",
    LostReason.REQUIREMENTS_CHANGED: "Requirements changed",
    LostReason.POOR_FIT: "Poor fit",
    LostReason.OTHER: "Other",
}


def _now() -> datetime:
    return datetime.now(UTC)


def effective_probability(deal: Deal, stage: PipelineStage) -> Decimal | None:
    return deal.probability if deal.probability is not None else stage.probability


def weighted(deal: Deal, stage: PipelineStage) -> Decimal | None:
    probability = effective_probability(deal, stage)
    if deal.value is None or probability is None:
        return None
    return (deal.value * probability / 100).quantize(Decimal("0.01"))


def attention_reasons(
    deal: Deal,
    next_task: Task | None,
    last_activity_at: datetime | None = None,
    *,
    now: datetime | None = None,
    inactive_days: int | None = None,
) -> list[str]:
    """§12's next-action engine applied to deals: every open deal needs an owner, a next task and
    an expected close date. With `inactive_days`, the follow-up engine's inactive-deal flag too:
    nothing logged and no stage move for that many days."""
    if deal.outcome is not StageOutcome.OPEN:
        return []
    reasons = []
    if deal.owner_id is None:
        reasons.append("no owner")
    if next_task is None:
        reasons.append("no next task")
    if deal.expected_close is None:
        reasons.append("no expected close date")
    if inactive_days is not None:
        since = last_touch(deal.stage_entered_at, last_activity_at)
        if is_quiet(since, now or _now(), inactive_days):
            reasons.append(f"inactive for {((now or _now()) - since).days} days")
    return reasons


# --- pipelines ---------------------------------------------------------------------------------


async def pipelines(db: AsyncSession) -> list[tuple[Pipeline, list[PipelineStage]]]:
    rows = (
        await db.execute(select(Pipeline).where(Pipeline.is_active).order_by(Pipeline.position))
    ).scalars()
    found = list(rows)
    stages: dict[uuid.UUID, list[PipelineStage]] = defaultdict(list)
    for stage in (
        await db.execute(
            select(PipelineStage)
            .where(PipelineStage.pipeline_id.in_([p.id for p in found]))
            .order_by(PipelineStage.position)
        )
    ).scalars():
        stages[stage.pipeline_id].append(stage)
    return [(p, stages[p.id]) for p in found]


async def update_stage(
    db: AsyncSession, *, user: User, stage_id: uuid.UUID, changes: dict[str, Any]
) -> PipelineStage:
    stage = await db.get(PipelineStage, stage_id)
    if stage is None:
        raise NotFound("Stage not found.")
    old = {k: _plain(getattr(stage, k)) for k in changes}
    for key, value in changes.items():
        setattr(stage, key, value)
    audit.record(
        db,
        action="pipeline_stage.updated",
        object_table="pipeline_stages",
        object_id=stage.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value=old,
        new_value={k: _plain(v) for k, v in changes.items()},
    )
    await db.commit()
    return stage


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value.value if hasattr(value, "value") else value


# --- reading deals -----------------------------------------------------------------------------


@dataclass
class DealView:
    deal: Deal
    account: Account
    stage: PipelineStage
    pipeline: Pipeline
    opportunity_name: str | None = None
    next_task: Task | None = None
    owner_name: str | None = None
    next_task_owner_name: str | None = None
    last_activity_at: datetime | None = None
    attention: list[str] = field(default_factory=list)
    project_id: uuid.UUID | None = None  # set once the won deal is converted (slice 4.1)


def _visible(stmt: Select[Any], user: User) -> Select[Any]:
    clause = access.visible(user)
    return stmt if clause is None else stmt.where(clause)


async def _next_tasks(db: AsyncSession, deals: list[Deal]) -> dict[uuid.UUID, Task]:
    """Each deal's next task: the earliest open task on the deal, or its opportunity's open
    next action."""
    if not deals:
        return {}
    ids = [d.id for d in deals]
    opp_to_deal = {d.opportunity_id: d.id for d in deals if d.opportunity_id}
    tasks = (
        await db.execute(
            select(Task)
            .where(
                Task.deleted_at.is_(None),
                Task.status.in_(OPEN_TASK),
                (Task.deal_id.in_(ids)) | (Task.opportunity_id.in_(list(opp_to_deal))),
            )
            .order_by(Task.due_at.asc().nulls_last(), Task.created_at)
        )
    ).scalars()
    found: dict[uuid.UUID, Task] = {}
    for task in tasks:
        deal_id = task.deal_id or opp_to_deal.get(task.opportunity_id)  # type: ignore[arg-type]
        if deal_id is not None:
            found.setdefault(deal_id, task)
    return found


async def _views(db: AsyncSession, rows: list[Any]) -> list[DealView]:
    deals = [r[0] for r in rows]
    next_tasks = await _next_tasks(db, deals)
    touched = await latest_touch(db, "deal_id", [d.id for d in deals])
    inactive_days = get_settings().inactive_deal_days
    opp_ids = [d.opportunity_id for d in deals if d.opportunity_id]
    opp_names = (
        dict(
            (
                await db.execute(
                    select(Opportunity.id, Opportunity.name).where(Opportunity.id.in_(opp_ids))
                )
            ).all()
        )
        if opp_ids
        else {}
    )
    owner_ids = {d.owner_id for d in deals if d.owner_id} | {
        t.owner_id for t in next_tasks.values() if t.owner_id
    }
    names = (
        dict((await db.execute(select(User.id, User.name).where(User.id.in_(owner_ids)))).all())
        if owner_ids
        else {}
    )
    won = [d.id for d in deals if d.outcome is StageOutcome.WON]
    projects = (
        dict(
            (
                await db.execute(
                    select(Project.deal_id, Project.id).where(
                        Project.deal_id.in_(won), Project.deleted_at.is_(None)
                    )
                )
            ).all()
        )
        if won
        else {}
    )
    views = []
    for deal, account, stage, pipeline in rows:
        task = next_tasks.get(deal.id)
        views.append(
            DealView(
                deal=deal,
                account=account,
                stage=stage,
                pipeline=pipeline,
                opportunity_name=opp_names.get(deal.opportunity_id)
                if deal.opportunity_id
                else None,
                next_task=task,
                owner_name=names.get(deal.owner_id) if deal.owner_id else None,
                next_task_owner_name=names.get(task.owner_id) if task and task.owner_id else None,
                last_activity_at=touched.get(deal.id),
                attention=attention_reasons(
                    deal, task, touched.get(deal.id), inactive_days=inactive_days
                ),
                project_id=projects.get(deal.id),
            )
        )
    return views


def _base() -> Select[Any]:
    stmt = (
        select(Deal, Account, PipelineStage, Pipeline)
        .join(Account, Account.id == Deal.account_id)
        .join(PipelineStage, PipelineStage.id == Deal.stage_id)
        .join(Pipeline, Pipeline.id == Deal.pipeline_id)
        .where(Deal.deleted_at.is_(None), Account.deleted_at.is_(None))
    )
    return cast(Select[Any], stmt)


async def list_deals(
    db: AsyncSession,
    *,
    user: User,
    pipeline_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
    owner: str | None = None,
    status: str = "open",
    limit: int = 500,
) -> list[DealView]:
    stmt = _visible(_base(), user)
    if pipeline_id is not None:
        stmt = stmt.where(Deal.pipeline_id == pipeline_id)
    if account_id is not None:
        stmt = stmt.where(Deal.account_id == account_id)
    if owner == "me":
        stmt = stmt.where(Deal.owner_id == user.id)
    elif owner == "unassigned":
        stmt = stmt.where(Deal.owner_id.is_(None))
    if status == "open":
        stmt = stmt.where(Deal.outcome.in_((StageOutcome.OPEN, StageOutcome.NURTURE)))
    elif status in ("won", "lost"):
        stmt = stmt.where(Deal.outcome == status)
    elif status == "closed":
        stmt = stmt.where(Deal.outcome.in_(CLOSED))
    stmt = stmt.order_by(PipelineStage.position, Deal.stage_entered_at, Deal.id).limit(limit)
    return await _views(db, list((await db.execute(stmt)).all()))


async def get_deal(db: AsyncSession, *, user: User, deal_id: uuid.UUID) -> DealView:
    row = (await db.execute(_visible(_base().where(Deal.id == deal_id), user))).first()
    if row is None:
        raise NotFound("Deal not found.")
    return (await _views(db, [row]))[0]


# --- writing deals -----------------------------------------------------------------------------


async def _active_owner(db: AsyncSession, owner_id: uuid.UUID | None) -> User | None:
    if owner_id is None:
        return None
    owner = await db.get(User, owner_id)
    if owner is None or not owner.is_active:
        raise ValidationFailed("The owner must be an active team member.", code="invalid_owner")
    return owner


def _default_kind(account: Account) -> PipelineKind:
    if account.account_type in (AccountType.CUSTOMER, AccountType.FORMER_CUSTOMER):
        return PipelineKind.EXPANSION
    if account.account_type is AccountType.PARTNER:
        return PipelineKind.PARTNERSHIP
    return PipelineKind.NEW_BUSINESS


@dataclass
class NewDeal:
    opportunity_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    pipeline_id: uuid.UUID | None = None
    name: str | None = None
    value: Decimal | None = None
    currency: str = "GBP"
    expected_close: date | None = None
    owner_id: uuid.UUID | None = None


async def create_deal(db: AsyncSession, *, user: User, data: NewDeal) -> uuid.UUID:
    opportunity = None
    if data.opportunity_id is not None:
        opportunity = await db.get(Opportunity, data.opportunity_id)
        if opportunity is None or opportunity.deleted_at is not None:
            raise NotFound("Opportunity not found.")
        existing = (
            await db.execute(
                select(Deal.id).where(
                    Deal.opportunity_id == opportunity.id, Deal.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise Conflict(
                "This opportunity already has a deal.", details={"deal_id": str(existing)}
            )
    account_id = opportunity.account_id if opportunity else data.account_id
    if account_id is None:
        raise ValidationFailed("Open a deal from an opportunity or on an account.")
    account = await db.get(Account, account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")

    if data.pipeline_id is not None:
        pipeline = await db.get(Pipeline, data.pipeline_id)
        if pipeline is None or not pipeline.is_active:
            raise NotFound("Pipeline not found.")
    else:
        pipeline = (
            (
                await db.execute(
                    select(Pipeline).where(
                        Pipeline.kind == _default_kind(account), Pipeline.is_active
                    )
                )
            )
            .scalars()
            .first()
        )
        if pipeline is None:
            raise NotFound("No pipeline is set up for this kind of account.")
    stages = (
        (
            await db.execute(
                select(PipelineStage)
                .where(PipelineStage.pipeline_id == pipeline.id)
                .order_by(PipelineStage.position)
            )
        )
        .scalars()
        .all()
    )
    open_stages = [s for s in stages if s.outcome is StageOutcome.OPEN]
    if not open_stages:
        raise ValidationFailed("This pipeline has no open stage to start in.")
    # An approved prospect's opportunity is already qualified: start there when the pipeline has it.
    stage = next(
        (s for s in open_stages if opportunity and s.key == opportunity.stage), open_stages[0]
    )

    owner_id = (
        data.owner_id
        or (opportunity.owner_id if opportunity else None)
        or account.owner_id
        or user.id
    )
    owner = await _active_owner(db, owner_id)
    deal = Deal(
        account_id=account.id,
        opportunity_id=opportunity.id if opportunity else None,
        pipeline_id=pipeline.id,
        stage_id=stage.id,
        name=(data.name or (opportunity.name if opportunity else account.name)).strip()[:200],
        value=data.value,
        currency=data.currency.upper(),
        expected_close=data.expected_close,
        owner_id=owner.id if owner else None,
        outcome=stage.outcome,
        stage_entered_at=_now(),
    )
    db.add(deal)
    await db.flush()
    db.add(
        DealStageChange(
            deal_id=deal.id, from_stage_id=None, to_stage_id=stage.id, changed_by_id=user.id
        )
    )
    value = f"{deal.currency} {deal.value:,.2f}" if deal.value is not None else "value unknown"
    timeline.add(
        db,
        account_id=account.id,
        event_type="deal.created",
        summary=f"Deal opened in {pipeline.name} at {stage.name}: {deal.name} ({value}).",
        actor_id=user.id,
        ref_table="deals",
        ref_id=deal.id,
    )
    audit.record(
        db,
        action="deal.created",
        object_table="deals",
        object_id=deal.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            "account_id": str(account.id),
            "opportunity_id": str(opportunity.id) if opportunity else None,
            "pipeline": pipeline.key,
            "stage": stage.key,
            "value": _plain(deal.value),
            "currency": deal.currency,
            "expected_close": _plain(deal.expected_close),
            "owner_id": _plain(deal.owner_id),
        },
    )
    await db.commit()
    return deal.id


EDITABLE = ("name", "value", "currency", "probability", "expected_close", "owner_id")


async def update_deal(
    db: AsyncSession, *, user: User, deal_id: uuid.UUID, changes: dict[str, Any]
) -> None:
    view = await get_deal(db, user=user, deal_id=deal_id)
    deal = view.deal
    if "owner_id" in changes:
        await _active_owner(db, changes["owner_id"])
    if changes.get("currency"):
        changes["currency"] = changes["currency"].upper()
    changed = {k: v for k, v in changes.items() if k in EDITABLE and getattr(deal, k) != v}
    if not changed:
        return
    old = {k: _plain(getattr(deal, k)) for k in changed}
    for key, value in changed.items():
        setattr(deal, key, value)
    audit.record(
        db,
        action="deal.updated",
        object_table="deals",
        object_id=deal.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value=old,
        new_value={k: _plain(v) for k, v in changed.items()},
    )
    if "value" in changed or "owner_id" in changed:
        what = ", ".join(k.replace("_id", "").replace("_", " ") for k in changed)
        timeline.add(
            db,
            account_id=deal.account_id,
            event_type="deal.updated",
            summary=f"Deal {deal.name} updated: {what}.",
            actor_id=user.id,
            ref_table="deals",
            ref_id=deal.id,
        )
    await db.commit()


async def move_deal(
    db: AsyncSession,
    *,
    user: User,
    deal_id: uuid.UUID,
    stage_id: uuid.UUID,
    lost_reason: LostReason | None,
    lost_note: str | None,
) -> None:
    view = await get_deal(db, user=user, deal_id=deal_id)
    deal, old_stage = view.deal, view.stage
    stage = await db.get(PipelineStage, stage_id)
    if stage is None or stage.pipeline_id != deal.pipeline_id:
        raise ValidationFailed("That stage is not in this deal's pipeline.", code="wrong_pipeline")
    if stage.id == deal.stage_id:
        raise Conflict(f"The deal is already at {stage.name}.")
    if stage.outcome is StageOutcome.LOST and lost_reason is None:
        raise ValidationFailed("Say why the deal was lost.", code="lost_reason_required")

    now = _now()
    deal.stage_id = stage.id
    deal.outcome = stage.outcome
    deal.stage_entered_at = now
    deal.closed_at = now if stage.outcome in CLOSED else None
    deal.lost_reason = lost_reason if stage.outcome is StageOutcome.LOST else None
    deal.lost_note = lost_note if stage.outcome is StageOutcome.LOST else None
    if deal.opportunity_id is not None:
        opportunity = await db.get(Opportunity, deal.opportunity_id)
        if opportunity is not None:
            opportunity.stage = stage.key  # the opportunity follows its deal
    db.add(
        DealStageChange(
            deal_id=deal.id, from_stage_id=old_stage.id, to_stage_id=stage.id, changed_by_id=user.id
        )
    )

    why = f" Reason: {LOST_REASON_LABELS[lost_reason]}." if deal.lost_reason and lost_reason else ""
    timeline.add(
        db,
        account_id=deal.account_id,
        event_type=f"deal.{stage.outcome.value}"
        if stage.outcome in CLOSED
        else "deal.stage_changed",
        summary=f"Deal {deal.name} moved from {old_stage.name} to {stage.name}.{why}",
        actor_id=user.id,
        ref_table="deals",
        ref_id=deal.id,
    )
    audit.record(
        db,
        action="deal.stage_changed",
        object_table="deals",
        object_id=deal.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value={"stage": old_stage.key, "outcome": old_stage.outcome.value},
        new_value={
            "stage": stage.key,
            "outcome": stage.outcome.value,
            "lost_reason": deal.lost_reason.value if deal.lost_reason else None,
        },
        reason=lost_note,
    )
    await db.commit()


# --- forecast ----------------------------------------------------------------------------------


def _money() -> Decimal:
    return Decimal("0.00")


@dataclass
class Month:
    value: Decimal = field(default_factory=_money)
    weighted: Decimal = field(default_factory=_money)
    count: int = 0


@dataclass
class CurrencyForecast:
    currency: str
    open_count: int = 0
    open_value: Decimal = field(default_factory=_money)
    unknown_value_count: int = 0  # open deals nobody has put a value on yet
    weighted_value: Decimal = field(default_factory=_money)
    unweighted_count: int = 0  # open deals with a value but no probability (partnerships)
    no_close_date_count: int = 0
    won_count: int = 0
    won_value: Decimal = field(default_factory=_money)
    won_unknown_value_count: int = 0
    lost_count: int = 0
    lost_value: Decimal = field(default_factory=_money)
    lost_unknown_value_count: int = 0
    months: dict[str, Month] = field(default_factory=dict)


async def forecast(
    db: AsyncSession, *, user: User, pipeline_id: uuid.UUID | None, year: int
) -> list[CurrencyForecast]:
    """Open pipeline by expected-close month, plus deals won and lost in `year`, per currency."""
    stmt = _visible(_base(), user)
    if pipeline_id is not None:
        stmt = stmt.where(Deal.pipeline_id == pipeline_id)
    out: dict[str, CurrencyForecast] = {}
    for deal, _account, stage, _pipeline in (await db.execute(stmt)).all():
        f = out.setdefault(deal.currency, CurrencyForecast(deal.currency))
        if deal.outcome is StageOutcome.OPEN:
            f.open_count += 1
            if deal.value is None:
                f.unknown_value_count += 1
                continue
            f.open_value += deal.value
            w = weighted(deal, stage)
            if w is None:
                f.unweighted_count += 1
            else:
                f.weighted_value += w
            if deal.expected_close is None:
                f.no_close_date_count += 1
                continue
            month = f.months.setdefault(deal.expected_close.strftime("%Y-%m"), Month())
            month.count += 1
            month.value += deal.value
            month.weighted += w or Decimal("0.00")
        elif deal.closed_at is not None and deal.closed_at.year == year:
            if deal.outcome is StageOutcome.WON:
                f.won_count += 1
                if deal.value is None:
                    f.won_unknown_value_count += 1
                else:
                    f.won_value += deal.value
            elif deal.outcome is StageOutcome.LOST:
                f.lost_count += 1
                if deal.value is None:
                    f.lost_unknown_value_count += 1
                else:
                    f.lost_value += deal.value
    return sorted(out.values(), key=lambda f: (-f.open_count, f.currency))
