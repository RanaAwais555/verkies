"""/tasks and /opportunities: the work that approval creates. /activities, /follow-ups and
contact editing (slice 3.2)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.accounts import contacts
from app.accounts.models import Contact
from app.accounts.schemas import ContactOut
from app.accounts.service import user_names
from app.auth.deps import AppSettings, DbSession, require_permission
from app.auth.models import User
from app.core.enums import TaskStatus
from app.core.errors import ValidationFailed
from app.crm import activities, service
from app.crm.follow_ups import follow_up_flags
from app.crm.schemas import (
    ActivityOut,
    CompleteTask,
    CreateTask,
    FlagOut,
    FollowUpsOut,
    LogActivity,
    NewContact,
    OpportunityOut,
    PersonOut,
    RelationshipOut,
    TaskOut,
    UpdateContact,
    UpdateTask,
)

router = APIRouter(tags=["crm"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]


async def _task_out(db: DbSession, task_id: uuid.UUID, user: User) -> TaskOut:
    task, account = await service.get_task(db, user=user, task_id=task_id)
    names = await user_names(db, {task.owner_id} if task.owner_id else set())
    return TaskOut.of(task, account_name=account.name, owner_name=names.get(task.owner_id))  # type: ignore[arg-type]


@router.get("/tasks")
async def list_tasks(
    user: Member,
    db: DbSession,
    mine: bool = True,
    status: TaskStatus | None = TaskStatus.OPEN,
    due_before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[TaskOut]:
    rows = await service.list_tasks(
        db, user=user, mine=mine, status=status, due_before=due_before, limit=limit
    )
    names = await user_names(db, {t.owner_id for t, _ in rows if t.owner_id})
    return [
        TaskOut.of(t, account_name=a.name, owner_name=names.get(t.owner_id) if t.owner_id else None)
        for t, a in rows
    ]


@router.post("/tasks", status_code=201)
async def create_task(body: CreateTask, user: Member, db: DbSession) -> TaskOut:
    task = await service.create_task(db, user=user, **body.model_dump())
    await db.commit()
    return await _task_out(db, task.id, user)


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: uuid.UUID, body: CompleteTask, user: Member, db: DbSession
) -> TaskOut:
    await service.complete_task(db, user=user, task_id=task_id, note=body.note)
    await db.commit()
    return await _task_out(db, task_id, user)


@router.patch("/tasks/{task_id}")
async def update_task(task_id: uuid.UUID, body: UpdateTask, user: Member, db: DbSession) -> TaskOut:
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes and changes["title"] is None:
        raise ValidationFailed("A task needs a title.")
    if not changes:
        raise ValidationFailed("Nothing to change.")
    await service.update_task(db, user=user, task_id=task_id, changes=changes)
    await db.commit()
    return await _task_out(db, task_id, user)


@router.get("/opportunities/requires-attention")
async def requiring_attention(
    user: Member, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[OpportunityOut]:
    found = await service.requiring_attention(db, user=user, limit=limit)
    labels = await service.opportunity_labels(db, [o for o, _, _ in found])
    return [
        OpportunityOut.of(o, reasons, account_name=a.name, labels=labels) for o, a, reasons in found
    ]


# --- activities (slice 3.2) --------------------------------------------------------------------


@router.post("/activities", status_code=201)
async def log_activity(body: LogActivity, user: Member, db: DbSession) -> ActivityOut:
    data = body.model_dump(exclude={"follow_up"})
    follow_up = (
        activities.FollowUp(**body.follow_up.model_dump()) if body.follow_up is not None else None
    )
    activity = await activities.log_activity(
        db, user=user, data=activities.NewActivity(**data, follow_up=follow_up)
    )
    await db.commit()
    found = await activities.list_activities(db, user=user, account_id=activity.account_id)
    return ActivityOut.of(next(v for v in found if v.activity.id == activity.id))


@router.get("/activities")
async def list_activities(
    user: Member,
    db: DbSession,
    account_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    opportunity_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ActivityOut]:
    found = await activities.list_activities(
        db,
        user=user,
        account_id=account_id,
        contact_id=contact_id,
        opportunity_id=opportunity_id,
        deal_id=deal_id,
        limit=limit,
    )
    return [ActivityOut.of(v) for v in found]


@router.get("/follow-ups")
async def follow_ups(
    user: Member,
    db: DbSession,
    settings: AppSettings,
    mine: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> FollowUpsOut:
    """Up to `limit` flags of each kind, most urgent first; `counts` says how many exist."""
    found = await follow_up_flags(db, user=user, settings=settings, mine=mine, limit=limit)
    flags = found.flags
    names = await user_names(db, {f.owner_id for f in flags if f.owner_id})
    return FollowUpsOut(
        flags=[
            FlagOut(
                kind=f.kind,
                account_id=f.account_id,
                account_name=f.account_name,
                ref_table=f.ref_table,
                ref_id=f.ref_id,
                title=f.title,
                detail=f.detail,
                since=f.since,
                owner=PersonOut(id=f.owner_id, name=names.get(f.owner_id)) if f.owner_id else None,
            )
            for f in flags
        ],
        counts=dict(found.counts),
        stale_opportunity_days=settings.stale_opportunity_days,
        inactive_deal_days=settings.inactive_deal_days,
    )


# --- contacts (slice 3.2) ----------------------------------------------------------------------


async def _contact_out(db: DbSession, contact: Contact) -> ContactOut:
    found = await activities.contact_relationships(db, [contact.id])
    return ContactOut.of(contact, RelationshipOut.of(found[contact.id]))


@router.post("/accounts/{account_id}/contacts", status_code=201)
async def add_contact(
    account_id: uuid.UUID, body: NewContact, user: Member, db: DbSession
) -> ContactOut:
    contact = await contacts.add_contact(
        db, user=user, account_id=account_id, data=body.model_dump()
    )
    await db.commit()
    return await _contact_out(db, contact)


@router.patch("/contacts/{contact_id}")
async def update_contact(
    contact_id: uuid.UUID, body: UpdateContact, user: Member, db: DbSession
) -> ContactOut:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationFailed("Nothing to change.")
    contact = await contacts.update_contact(db, user=user, contact_id=contact_id, changes=changes)
    await db.commit()
    return await _contact_out(db, contact)
