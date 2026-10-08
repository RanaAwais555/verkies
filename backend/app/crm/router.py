"""/tasks and /opportunities: the work that approval creates."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.accounts.service import user_names
from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.core.enums import TaskStatus
from app.core.errors import ValidationFailed
from app.crm import service
from app.crm.schemas import CompleteTask, CreateTask, OpportunityOut, TaskOut, UpdateTask

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
