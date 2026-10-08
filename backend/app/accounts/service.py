"""Account list and Account 360 reads. Writes happen through approval and the CRM services."""

import uuid
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account, AccountDomain, Contact
from app.audit.models import AuditLog
from app.auth.models import User
from app.briefs.models import LeadBrief
from app.core.enums import AccountType
from app.core.errors import NotFound
from app.core.search import contains_pattern
from app.crm.models import Lead, Opportunity, Task, TimelineEvent
from app.crm.service import attention_reasons, opportunity_labels
from app.research.models import ResearchRun


def _visible(stmt: Select[Any], user: User) -> Select[Any]:
    clause = access.visible(user)
    return stmt if clause is None else stmt.where(clause)


async def list_accounts(
    db: AsyncSession,
    *,
    user: User,
    query: str | None,
    account_type: AccountType | None,
    owner: str | None,
    limit: int,
    offset: int,
) -> list[Account]:
    stmt = select(Account).where(Account.deleted_at.is_(None))
    stmt = _visible(stmt, user)
    if query and query.strip():
        pattern = contains_pattern(query)
        domains = select(AccountDomain.account_id).where(AccountDomain.domain.ilike(pattern))
        stmt = stmt.where(or_(Account.name.ilike(pattern), Account.id.in_(domains)))
    if account_type is not None:
        stmt = stmt.where(Account.account_type == account_type)
    if owner == "me":
        stmt = stmt.where(Account.owner_id == user.id)
    elif owner == "unassigned":
        stmt = stmt.where(Account.owner_id.is_(None))
    stmt = (
        stmt.order_by(Account.priority_score.desc().nulls_last(), Account.name, Account.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await db.execute(stmt)).scalars())


async def get_account(db: AsyncSession, *, user: User, account_id: uuid.UUID) -> Account:
    account = await db.get(Account, account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")
    return account


async def account_360(db: AsyncSession, account: Account) -> dict[str, Any]:
    async def rows(stmt: Select[Any]) -> list[Any]:
        return list((await db.execute(stmt)).scalars())

    domains = await rows(
        select(AccountDomain)
        .where(AccountDomain.account_id == account.id)
        .order_by(AccountDomain.is_primary.desc(), AccountDomain.domain)
    )
    leads = await rows(
        select(Lead)
        .where(Lead.account_id == account.id, Lead.deleted_at.is_(None))
        .order_by(Lead.created_at.desc())
    )
    opportunities = await rows(
        select(Opportunity)
        .where(Opportunity.account_id == account.id, Opportunity.deleted_at.is_(None))
        .order_by(Opportunity.created_at.desc())
    )
    contacts = await rows(
        select(Contact)
        .where(Contact.account_id == account.id, Contact.deleted_at.is_(None))
        .order_by(Contact.confidence.desc(), Contact.name)
    )
    tasks = await rows(
        select(Task)
        .where(Task.account_id == account.id, Task.deleted_at.is_(None))
        .order_by(Task.completed_at.desc().nulls_first(), Task.due_at.asc().nulls_last())
    )
    runs = await rows(
        select(ResearchRun)
        .where(ResearchRun.account_id == account.id)
        .order_by(ResearchRun.created_at.desc())
    )
    brief_run = (
        await db.execute(
            select(LeadBrief.research_run_id)
            .where(LeadBrief.account_id == account.id)
            .order_by(LeadBrief.generated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    task_by_id = {t.id: t for t in tasks}
    owner_ids = {
        account.owner_id,
        *(t.owner_id for t in tasks),
        *(o.owner_id for o in opportunities),
    }
    owner_ids |= {lead.owner_id for lead in leads}
    owners = await user_names(db, {i for i in owner_ids if i})
    return {
        "domains": domains,
        "leads": leads,
        "opportunities": [
            (o, attention_reasons(o, task_by_id.get(o.next_action_task_id))) for o in opportunities
        ],
        "contacts": contacts,
        "tasks": tasks,
        "research_runs": runs,
        "latest_brief_run_id": brief_run,
        "labels": await opportunity_labels(db, opportunities),
        "owners": owners,
    }


async def user_names(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    found = await db.execute(select(User.id, User.name).where(User.id.in_(ids)))
    return {i: n for i, n in found.all()}


async def timeline_of(db: AsyncSession, account_id: uuid.UUID, limit: int) -> list[TimelineEvent]:
    return list(
        (
            await db.execute(
                select(TimelineEvent)
                .where(TimelineEvent.account_id == account_id)
                .order_by(TimelineEvent.occurred_at.desc(), TimelineEvent.id.desc())
                .limit(limit)
            )
        ).scalars()
    )


async def audit_of(db: AsyncSession, account: Account, limit: int) -> list[AuditLog]:
    """Audit entries for the account and everything hanging off it."""
    related: list[uuid.UUID] = [account.id]
    for model in (Lead, Opportunity, Task, Contact, ResearchRun):
        related += list(
            (await db.execute(select(model.id).where(model.account_id == account.id))).scalars()
        )
    return list(
        (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.object_id.in_(related))
                .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
                .limit(limit)
            )
        ).scalars()
    )


async def count_open_tasks(db: AsyncSession, account_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not account_ids:
        return {}
    found = await db.execute(
        select(Task.account_id, func.count())
        .where(
            Task.account_id.in_(account_ids),
            Task.deleted_at.is_(None),
            Task.status.in_(("open", "in_progress")),
        )
        .group_by(Task.account_id)
    )
    return {a: n for a, n in found.all()}
