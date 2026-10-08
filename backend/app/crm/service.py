"""Tasks and the "opportunity requires attention" rule (§12, PRODUCT_SPEC.md §5).

Every open opportunity needs a next-action task that is open, has an owner and has a due
date; any opportunity without one is listed as requiring attention.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account
from app.audit import service as audit
from app.auth.models import User
from app.catalogue.models import Service
from app.core.enums import AuditSource, TaskStatus
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.crm import timeline
from app.crm.models import Opportunity, Task
from app.opportunities.models import OpportunityCategory

OPEN = (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)


def _now() -> datetime:
    return datetime.now(UTC)


def attention_reasons(opportunity: Opportunity, task: Task | None) -> list[str]:
    if task is None or task.deleted_at is not None:
        return ["no next action"]
    if task.status not in OPEN:
        return ["next action is closed; set a new one"]
    reasons = []
    if task.owner_id is None:
        reasons.append("next action has no owner")
    if task.due_at is None:
        reasons.append("next action has no due date")
    return reasons


def _task_scope(user: User) -> list[ColumnElement[bool]]:
    """Conditions limiting a Task-joined-to-Account query to what the user may see."""
    conditions: list[ColumnElement[bool]] = [
        Task.deleted_at.is_(None),
        Account.deleted_at.is_(None),
    ]
    clause = access.visible(user)
    if clause is not None:
        conditions.append(clause)
    return conditions


async def list_tasks(
    db: AsyncSession,
    *,
    user: User,
    mine: bool,
    status: TaskStatus | None,
    due_before: datetime | None,
    limit: int,
) -> list[tuple[Task, Account]]:
    stmt = (
        select(Task, Account).join(Account, Account.id == Task.account_id).where(*_task_scope(user))
    )
    if mine:
        stmt = stmt.where(Task.owner_id == user.id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if due_before is not None:
        stmt = stmt.where(Task.due_at < due_before)
    stmt = stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at).limit(limit)
    return [(t, a) for t, a in (await db.execute(stmt)).all()]


async def get_task(db: AsyncSession, *, user: User, task_id: uuid.UUID) -> tuple[Task, Account]:
    found = (
        await db.execute(
            select(Task, Account)
            .join(Account, Account.id == Task.account_id)
            .where(Task.id == task_id, *_task_scope(user))
            .with_for_update(of=Task)
        )
    ).first()
    if found is None:
        raise NotFound("Task not found.")
    return found[0], found[1]


async def complete_task(
    db: AsyncSession, *, user: User, task_id: uuid.UUID, note: str | None
) -> Task:
    task, account = await get_task(db, user=user, task_id=task_id)
    if task.status not in OPEN:
        raise Conflict(f"This task is already {task.status.value}.")
    old = task.status.value
    task.status = TaskStatus.DONE
    task.completed_at = _now()
    account.last_activity_at = task.completed_at
    await _refresh_next_activity(db, account, ignore=task.id)
    timeline.add(
        db,
        account_id=account.id,
        event_type="task.completed",
        summary=f"Task completed: {task.title}"
        + (f" ({note.strip()})" if note and note.strip() else ""),
        actor_id=user.id,
        ref_table="tasks",
        ref_id=task.id,
    )
    audit.record(
        db,
        action="task.completed",
        object_table="tasks",
        object_id=task.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value={"status": old},
        new_value={"status": TaskStatus.DONE.value},
        reason=note,
    )
    return task


async def create_task(
    db: AsyncSession,
    *,
    user: User,
    account_id: uuid.UUID,
    title: str,
    owner_id: uuid.UUID | None,
    due_at: datetime | None,
    opportunity_id: uuid.UUID | None,
    description: str | None,
) -> Task:
    """A new task on an account. With an opportunity, it becomes that opportunity's next
    action, which clears "requires attention" once it has an owner and a due date."""
    account = await db.get(Account, account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")
    owner = await db.get(User, owner_id) if owner_id is not None else None
    if owner_id is not None and (owner is None or not owner.is_active):
        raise ValidationFailed("The owner must be an active team member.", code="invalid_owner")
    opportunity = None
    if opportunity_id is not None:
        opportunity = await db.get(Opportunity, opportunity_id)
        if opportunity is None or opportunity.account_id != account.id:
            raise ValidationFailed("That opportunity is not on this account.")
    task = Task(
        account_id=account.id,
        opportunity_id=opportunity_id,
        lead_id=opportunity.lead_id if opportunity else None,
        title=title.strip()[:200],
        description=description,
        owner_id=owner_id,
        due_at=due_at,
    )
    db.add(task)
    await db.flush()
    if opportunity is not None:
        opportunity.next_action_task_id = task.id
    await _refresh_next_activity(db, account)
    owner_name = owner.name if owner else "nobody"
    due = due_at.date().isoformat() if due_at else "no date"
    timeline.add(
        db,
        account_id=account.id,
        event_type="task.created",
        summary=f"Task for {owner_name}, due {due}: {task.title}",
        actor_id=user.id,
        ref_table="tasks",
        ref_id=task.id,
    )
    audit.record(
        db,
        action="task.created",
        object_table="tasks",
        object_id=task.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            "title": task.title,
            "owner_id": str(owner_id) if owner_id else None,
            "due_at": due_at.isoformat() if due_at else None,
            "opportunity_id": str(opportunity_id) if opportunity_id else None,
        },
    )
    return task


async def update_task(
    db: AsyncSession, *, user: User, task_id: uuid.UUID, changes: dict[str, Any]
) -> Task:
    """Reassign, reschedule or retitle an open task."""
    task, account = await get_task(db, user=user, task_id=task_id)
    if task.status not in OPEN:
        raise Conflict(f"This task is {task.status.value} and can no longer be changed.")
    if "owner_id" in changes:
        owner = await db.get(User, changes["owner_id"]) if changes["owner_id"] else None
        if changes["owner_id"] and (owner is None or not owner.is_active):
            raise ValidationFailed("The owner must be an active team member.", code="invalid_owner")
    old = {k: _plain(getattr(task, k)) for k in changes}
    for key, value in changes.items():
        setattr(task, key, value)
    new = {k: _plain(v) for k, v in changes.items()}
    if old == new:
        return task
    await _refresh_next_activity(db, account)
    timeline.add(
        db,
        account_id=account.id,
        event_type="task.updated",
        summary=f"Task updated: {task.title} ({', '.join(sorted(changes))} changed).",
        actor_id=user.id,
        ref_table="tasks",
        ref_id=task.id,
    )
    audit.record(
        db,
        action="task.updated",
        object_table="tasks",
        object_id=task.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value=old,
        new_value=new,
    )
    return task


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


async def _refresh_next_activity(
    db: AsyncSession, account: Account, ignore: uuid.UUID | None = None
) -> None:
    await db.flush()
    stmt = select(Task.due_at).where(
        Task.account_id == account.id,
        Task.deleted_at.is_(None),
        Task.status.in_(OPEN),
        Task.due_at.is_not(None),
    )
    if ignore is not None:
        stmt = stmt.where(Task.id != ignore)
    account.next_activity_at = (
        await db.execute(stmt.order_by(Task.due_at).limit(1))
    ).scalar_one_or_none()


async def requiring_attention(
    db: AsyncSession, *, user: User, limit: int
) -> list[tuple[Opportunity, Account, list[str]]]:
    stmt = (
        select(Opportunity, Account, Task)
        .join(Account, Account.id == Opportunity.account_id)
        .outerjoin(Task, Task.id == Opportunity.next_action_task_id)
        .where(Opportunity.deleted_at.is_(None), Account.deleted_at.is_(None))
        .order_by(Account.priority_score.desc().nulls_last(), Opportunity.created_at)
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    found: list[tuple[Opportunity, Account, list[str]]] = []
    for opportunity, account, task in (await db.execute(stmt)).all():
        reasons = attention_reasons(opportunity, task)
        if reasons:
            found.append((opportunity, account, reasons))
            if len(found) >= limit:
                break
    return found


async def opportunity_labels(
    db: AsyncSession, opportunities: list[Opportunity]
) -> dict[uuid.UUID, tuple[str | None, str | None]]:
    """Category and service names for display, keyed by opportunity id."""
    if not opportunities:
        return {}
    categories = {
        c.id: c.name
        for c in (
            await db.execute(
                select(OpportunityCategory).where(
                    OpportunityCategory.id.in_({o.category_id for o in opportunities})
                )
            )
        ).scalars()
    }
    services = {
        s.id: s.name
        for s in (
            await db.execute(
                select(Service).where(Service.id.in_({o.service_id for o in opportunities}))
            )
        ).scalars()
    }
    return {
        o.id: (
            categories.get(o.category_id) if o.category_id else None,
            services.get(o.service_id) if o.service_id else None,
        )
        for o in opportunities
    }
