"""Task and opportunity API models."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import (
    ActivityKind,
    CallOutcome,
    DecisionMakerRole,
    VerificationStatus,
)
from app.crm.activities import ActivityView, Relationship
from app.crm.models import Opportunity, Task


def _num(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


class TaskOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    account_name: str | None = None
    lead_id: uuid.UUID | None
    opportunity_id: uuid.UUID | None
    deal_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
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
            deal_id=t.deal_id,
            project_id=t.project_id,
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
    deal_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=4000)


class UpdateTask(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    owner_id: uuid.UUID | None = None
    due_at: datetime | None = None


class RelationshipOut(BaseModel):
    """Relationship tracking (master context §12), computed from logged activities."""

    first_interaction_at: datetime | None
    latest_interaction_at: datetime | None
    days_since_contact: int | None
    interactions: int
    last_reply_at: datetime | None
    attempts_since_reply: int
    response_status: str

    @classmethod
    def of(cls, r: Relationship, now: datetime | None = None) -> "RelationshipOut":
        now = now or datetime.now(UTC)
        return cls(
            first_interaction_at=r.first_interaction_at,
            latest_interaction_at=r.latest_interaction_at,
            days_since_contact=(now - r.latest_interaction_at).days
            if r.latest_interaction_at
            else None,
            interactions=r.interactions,
            last_reply_at=r.last_reply_at,
            attempts_since_reply=r.attempts_since_reply,
            response_status=r.response_status,
        )


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str | None


class ActivityOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    account_name: str
    kind: str
    channel: str
    direction: str
    call_outcome: str | None
    occurred_at: datetime
    summary: str
    contact: PersonOut | None
    opportunity_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    logged_by: PersonOut | None
    created_at: datetime

    @classmethod
    def of(cls, v: ActivityView) -> "ActivityOut":
        a = v.activity
        return cls(
            id=a.id,
            account_id=a.account_id,
            account_name=v.account_name,
            kind=a.activity_type,
            channel=a.channel.value,
            direction=a.direction.value,
            call_outcome=a.payload.get("call_outcome"),
            occurred_at=a.occurred_at,
            summary=a.summary,
            contact=PersonOut(id=a.contact_id, name=v.contact_name) if a.contact_id else None,
            opportunity_id=a.opportunity_id,
            deal_id=a.deal_id,
            logged_by=PersonOut(id=a.actor_id, name=v.actor_name) if a.actor_id else None,
            created_at=a.created_at,
        )


class FollowUpIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime
    owner_id: uuid.UUID | None = None


class LogActivity(BaseModel):
    account_id: uuid.UUID
    kind: ActivityKind
    summary: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime | None = None
    contact_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    call_outcome: CallOutcome | None = None
    message_channel: Literal["email", "linkedin", "whatsapp", "other"] | None = None
    received: bool = False
    follow_up: FollowUpIn | None = None


class FlagOut(BaseModel):
    kind: str
    account_id: uuid.UUID
    account_name: str
    ref_table: str
    ref_id: uuid.UUID
    title: str
    detail: str
    since: datetime | None
    owner: PersonOut | None


class FollowUpsOut(BaseModel):
    flags: list[FlagOut]
    counts: dict[str, int]
    stale_opportunity_days: int
    inactive_deal_days: int


class ContactFields(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    email: str | None = Field(
        default=None, max_length=320, pattern=r"^([^@\s]+@[^@\s]+\.[^@\s]+)?$"
    )
    phone: str | None = Field(default=None, max_length=40, pattern=r"^[0-9+()\-.\s]*$")
    linkedin_url: str | None = Field(default=None, max_length=500, pattern=r"^(https?://\S+)?$")
    decision_maker_role: DecisionMakerRole | None = None
    notes: str | None = Field(default=None, max_length=4000)


class NewContact(ContactFields):
    name: str = Field(min_length=1, max_length=200)


class UpdateContact(ContactFields):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    verification_status: VerificationStatus | None = None
