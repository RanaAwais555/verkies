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
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account
from app.auth.models import User
from app.config import Settings
from app.core.enums import StageOutcome
from app.crm import service as crm
from app.crm.activities import latest_touch
from app.crm.models import Opportunity, Task
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


def _days(since: datetime, now: datetime) -> int:
    return (now - since).days


def _overdue_detail(due_at: datetime | None, now: datetime) -> str:
    days = _days(due_at, now) if due_at else 0
    if days == 0:
        return "Due earlier today"
    return f"Overdue by {days} day{'s' if days != 1 else ''}"


async def overdue_follow_ups(
    db: AsyncSession, *, user: User, mine: bool, now: datetime
) -> list[Flag]:
    stmt = (
        select(Task, Account)
        .join(Account, Account.id == Task.account_id)
        .where(
            Task.deleted_at.is_(None),
            Account.deleted_at.is_(None),
            Task.status.in_(crm.OPEN),
            Task.due_at < now,
        )
        .order_by(Task.due_at)
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    if mine:
        stmt = stmt.where(crm.responsible(Task.owner_id) == user.id)
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
        for task, account in (await db.execute(stmt)).all()
    ]


async def no_next_action(db: AsyncSession, *, user: User, mine: bool, limit: int) -> list[Flag]:
    return [
        Flag(
            kind="no_next_action",
            account_id=account.id,
            account_name=account.name,
            ref_table="opportunities",
            ref_id=opportunity.id,
            title=opportunity.name,
            detail="; ".join(reasons),
            since=None,
            owner_id=opportunity.owner_id or account.owner_id,
        )
        for opportunity, account, reasons in await crm.requiring_attention(
            db, user=user, limit=limit, mine=mine
        )
    ]


def _quiet_detail(since: datetime, now: datetime) -> str:
    return f"Nothing logged for {_days(since, now)} days"


async def stale_opportunities(
    db: AsyncSession, *, user: User, mine: bool, now: datetime, days: int
) -> list[Flag]:
    with_deal = select(Deal.opportunity_id).where(
        Deal.deleted_at.is_(None), Deal.opportunity_id.is_not(None)
    )
    stmt = (
        select(Opportunity, Account)
        .join(Account, Account.id == Opportunity.account_id)
        .where(
            Opportunity.deleted_at.is_(None),
            Account.deleted_at.is_(None),
            Opportunity.id.not_in(with_deal),
            # Only an opportunity older than the window can have been quiet for all of it.
            Opportunity.created_at <= now - timedelta(days=days),
        )
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    if mine:
        stmt = stmt.where(crm.responsible(Opportunity.owner_id) == user.id)
    rows = (await db.execute(stmt)).all()
    touched = await latest_touch(db, "opportunity_id", [o.id for o, _ in rows])
    flags = []
    for opportunity, account in rows:
        since = last_touch(opportunity.created_at, touched.get(opportunity.id))
        if is_quiet(since, now, days):
            flags.append(
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
            )
    return sorted(flags, key=lambda f: f.since or now)


async def inactive_deals(
    db: AsyncSession, *, user: User, mine: bool, now: datetime, days: int
) -> list[Flag]:
    stmt = (
        select(Deal, Account)
        .join(Account, Account.id == Deal.account_id)
        .where(
            Deal.deleted_at.is_(None),
            Account.deleted_at.is_(None),
            Deal.outcome == StageOutcome.OPEN,
            Deal.stage_entered_at <= now - timedelta(days=days),
        )
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    if mine:
        stmt = stmt.where(crm.responsible(Deal.owner_id) == user.id)
    rows = (await db.execute(stmt)).all()
    touched = await latest_touch(db, "deal_id", [d.id for d, _ in rows])
    flags = []
    for deal, account in rows:
        since = last_touch(deal.stage_entered_at, touched.get(deal.id))
        if is_quiet(since, now, days):
            flags.append(
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
            )
    return sorted(flags, key=lambda f: f.since or now)


async def follow_up_flags(
    db: AsyncSession, *, user: User, settings: Settings, mine: bool, limit: int = 200
) -> list[Flag]:
    now = _now()
    return [
        *await overdue_follow_ups(db, user=user, mine=mine, now=now),
        *await no_next_action(db, user=user, mine=mine, limit=limit),
        *await stale_opportunities(
            db, user=user, mine=mine, now=now, days=settings.stale_opportunity_days
        ),
        *await inactive_deals(db, user=user, mine=mine, now=now, days=settings.inactive_deal_days),
    ]
