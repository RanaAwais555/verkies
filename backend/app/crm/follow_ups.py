"""The follow-up engine's flags (master context §12; slice 3.2).

Four flags, each computed from data on every read:

- **Overdue follow-up:** an open task whose due date has passed.
- **No next action:** an open opportunity without an open next action that has an owner and a
  due date (§12's next-action engine).
- **Stale opportunity:** an open opportunity with no deal where nothing has happened for
  `stale_opportunity_days`. Once an opportunity has a deal, the deal is what gets worked, so the
  deal is flagged instead.
- **Inactive deal:** an open deal where nothing has happened for `inactive_deal_days`.

"Something happened" means a logged activity, a completed task or, for a deal, a stage move; a
record's own creation starts the clock. Nothing here sends anything: a flag asks a person to act.

The database does the filtering, ordering and counting (slice 7.5): each kind returns its most
urgent `limit` flags and the exact number that exist, so the list stays fast however many there
are.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account
from app.auth.models import User
from app.config import Settings
from app.core.enums import StageOutcome, TaskStatus
from app.crm import service as crm
from app.crm.models import Activity, Opportunity, Task
from app.deals.models import Deal

FlagKind = Literal["overdue_follow_up", "no_next_action", "stale_opportunity", "inactive_deal"]
KINDS: tuple[FlagKind, ...] = (
    "overdue_follow_up",
    "no_next_action",
    "stale_opportunity",
    "inactive_deal",
)


def _now() -> datetime:
    return datetime.now(UTC)


def is_quiet(last_touch: datetime, now: datetime, days: int) -> bool:
    """True once `days` whole days have passed since the last touch."""
    return now - last_touch >= timedelta(days=days)


def last_touch(created: datetime, *touches: datetime | None) -> datetime:
    return max([created, *(t for t in touches if t is not None)])


@dataclass
class Flag:
    kind: FlagKind
    account_id: uuid.UUID
    account_name: str
    ref_table: str
    ref_id: uuid.UUID
    title: str
    detail: str
    since: datetime | None
    owner_id: uuid.UUID | None


@dataclass
class FollowUps:
    flags: list[Flag] = field(default_factory=list)
    # How many of each kind exist, which can be more than the flags returned.
    counts: dict[str, int] = field(default_factory=dict)


def _days(since: datetime, now: datetime) -> int:
    return (now - since).days


def _overdue_detail(due_at: datetime | None, now: datetime) -> str:
    days = _days(due_at, now) if due_at else 0
    if days == 0:
        return "Due earlier today"
    return f"Overdue by {days} day{'s' if days != 1 else ''}"


def _quiet_detail(since: datetime, now: datetime) -> str:
    return f"Nothing logged for {_days(since, now)} days"


async def _page(db: AsyncSession, stmt: Any, limit: int) -> tuple[list[Any], int]:
    """The first `limit` rows of an ordered statement, and how many rows it has in all."""
    total = (
        await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))
    ).scalar_one()
    rows = list((await db.execute(stmt.limit(limit))).all()) if total else []
    return rows, total


def _scoped(stmt: Any, user: User, owner: Any, mine: bool) -> Any:
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    if mine:
        stmt = stmt.where(crm.responsible(owner) == user.id)
    return stmt


def _last_touch(column: str, record_id: Any, start: Any) -> ColumnElement[Any]:
    """The record's start, its latest activity or its latest completed task, whichever is
    latest (last_touch in SQL). `column` is "opportunity_id" or "deal_id"."""
    activity = (
        select(func.max(Activity.occurred_at))
        .where(getattr(Activity, column) == record_id)
        .scalar_subquery()
    )
    task = (
        select(func.max(Task.completed_at))
        .where(
            getattr(Task, column) == record_id,
            Task.deleted_at.is_(None),
            Task.status == TaskStatus.DONE,
        )
        .scalar_subquery()
    )
    return func.greatest(start, activity, task)  # NULLs are ignored


async def overdue_follow_ups(
    db: AsyncSession, *, user: User, mine: bool, now: datetime, limit: int
) -> tuple[list[Flag], int]:
    stmt = (
        select(Task, Account)
        .join(Account, Account.id == Task.account_id)
        .where(
            Task.deleted_at.is_(None),
            Account.deleted_at.is_(None),
            Task.status.in_(crm.OPEN),
            Task.due_at < now,
        )
        .order_by(Task.due_at, Task.id)
    )
    rows, total = await _page(db, _scoped(stmt, user, Task.owner_id, mine), limit)
    return [
        Flag(
            kind="overdue_follow_up",
            account_id=account.id,
            account_name=account.name,
            ref_table="tasks",
            ref_id=task.id,
            title=task.title,
            detail=_overdue_detail(task.due_at, now),
            since=task.due_at,
            owner_id=task.owner_id or account.owner_id,
        )
        for task, account in rows
    ], total


async def no_next_action(
    db: AsyncSession, *, user: User, mine: bool, limit: int
) -> tuple[list[Flag], int]:
    rows, total = await _page(db, crm.attention_statement(user, mine=mine), limit)
    return [
        Flag(
            kind="no_next_action",
            account_id=account.id,
            account_name=account.name,
            ref_table="opportunities",
            ref_id=opportunity.id,
            title=opportunity.name,
            detail="; ".join(crm.attention_reasons(opportunity, task)),
            since=None,
            owner_id=opportunity.owner_id or account.owner_id,
        )
        for opportunity, account, task in rows
    ], total


async def stale_opportunities(
    db: AsyncSession, *, user: User, mine: bool, now: datetime, days: int, limit: int
) -> tuple[list[Flag], int]:
    with_deal = select(Deal.opportunity_id).where(
        Deal.deleted_at.is_(None), Deal.opportunity_id.is_not(None)
    )
    touched = _last_touch("opportunity_id", Opportunity.id, Opportunity.created_at)
    stmt = (
        select(Opportunity, Account, touched.label("since"))
        .join(Account, Account.id == Opportunity.account_id)
        .where(
            Opportunity.deleted_at.is_(None),
            Account.deleted_at.is_(None),
            Opportunity.id.not_in(with_deal),
            touched <= now - timedelta(days=days),
        )
        .order_by(touched, Opportunity.id)
    )
    rows, total = await _page(db, _scoped(stmt, user, Opportunity.owner_id, mine), limit)
    return [
        Flag(
            kind="stale_opportunity",
            account_id=account.id,
            account_name=account.name,
            ref_table="opportunities",
            ref_id=opportunity.id,
            title=opportunity.name,
            detail=_quiet_detail(since, now),
            since=since,
            owner_id=opportunity.owner_id or account.owner_id,
        )
        for opportunity, account, since in rows
    ], total


async def inactive_deals(
    db: AsyncSession, *, user: User, mine: bool, now: datetime, days: int, limit: int
) -> tuple[list[Flag], int]:
    touched = _last_touch("deal_id", Deal.id, Deal.stage_entered_at)
    stmt = (
        select(Deal, Account, touched.label("since"))
        .join(Account, Account.id == Deal.account_id)
        .where(
            Deal.deleted_at.is_(None),
            Account.deleted_at.is_(None),
            Deal.outcome == StageOutcome.OPEN,
            touched <= now - timedelta(days=days),
        )
        .order_by(touched, Deal.id)
    )
    rows, total = await _page(db, _scoped(stmt, user, Deal.owner_id, mine), limit)
    return [
        Flag(
            kind="inactive_deal",
            account_id=account.id,
            account_name=account.name,
            ref_table="deals",
            ref_id=deal.id,
            title=deal.name,
            detail=_quiet_detail(since, now),
            since=since,
            owner_id=deal.owner_id or account.owner_id,
        )
        for deal, account, since in rows
    ], total


async def follow_up_flags(
    db: AsyncSession, *, user: User, settings: Settings, mine: bool, limit: int = 100
) -> FollowUps:
    """Up to `limit` flags of each kind, most urgent first, and how many of each exist."""
    now = _now()
    found = {
        "overdue_follow_up": await overdue_follow_ups(
            db, user=user, mine=mine, now=now, limit=limit
        ),
        "no_next_action": await no_next_action(db, user=user, mine=mine, limit=limit),
        "stale_opportunity": await stale_opportunities(
            db, user=user, mine=mine, now=now, days=settings.stale_opportunity_days, limit=limit
        ),
        "inactive_deal": await inactive_deals(
            db, user=user, mine=mine, now=now, days=settings.inactive_deal_days, limit=limit
        ),
    }
    return FollowUps(
        flags=[flag for kind in KINDS for flag in found[kind][0]],
        counts={kind: found[kind][1] for kind in KINDS},
    )
