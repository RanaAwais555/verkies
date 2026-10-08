"""Task and opportunity API models."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.crm.models import Opportunity, Task


def _num(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


class TaskOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    account_name: str | None = None
    lead_id: uuid.UUID | None
    opportunity_id: uuid.UUID | None
    title: str
    description: str | None
    owner_id: uuid.UUID | None
    owner_name: str | None = None
    due_at: datetime | None
    priority: str
    status: str
    completed_at: datetime | None
    created_at: datetime

    @classmethod
    def of(
        cls, t: Task, *, account_name: str | None = None, owner_name: str | None = None
    ) -> "TaskOut":
        return cls(
            id=t.id,
            account_id=t.account_id,
            account_name=account_name,
            lead_id=t.lead_id,
            opportunity_id=t.opportunity_id,
            title=t.title,
            description=t.description,
            owner_id=t.owner_id,
            owner_name=owner_name,
            due_at=t.due_at,
            priority=t.priority.value,
            status=t.status.value,
            completed_at=t.completed_at,
            created_at=t.created_at,
        )


class OpportunityOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    account_name: str | None = None
    lead_id: uuid.UUID | None
    name: str
    problem: str
    category_id: uuid.UUID | None
    category_name: str | None = None
    service_id: uuid.UUID | None
    service_name: str | None = None
    stage: str
    owner_id: uuid.UUID | None
    estimated_value: float | None
    probability: float | None
    next_action_task_id: uuid.UUID | None
    requires_attention: list[str]
    created_at: datetime

    @classmethod
    def of(
        cls,
        o: Opportunity,
        reasons: list[str],
        *,
        account_name: str | None = None,
        labels: dict[uuid.UUID, tuple[str | None, str | None]] | None = None,
    ) -> "OpportunityOut":
        category_name, service_name = (labels or {}).get(o.id, (None, None))
        return cls(
            category_name=category_name,
            service_name=service_name,
            id=o.id,
            account_id=o.account_id,
            account_name=account_name,
            lead_id=o.lead_id,
            name=o.name,
            problem=o.problem,
            category_id=o.category_id,
            service_id=o.service_id,
            stage=o.stage,
            owner_id=o.owner_id,
            estimated_value=_num(o.estimated_value),
            probability=_num(o.probability),
            next_action_task_id=o.next_action_task_id,
            requires_attention=reasons,
            created_at=o.created_at,
        )


class CompleteTask(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class CreateTask(BaseModel):
    account_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    owner_id: uuid.UUID | None = None
    due_at: datetime | None = None
    opportunity_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=4000)


class UpdateTask(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    owner_id: uuid.UUID | None = None
    due_at: datetime | None = None
