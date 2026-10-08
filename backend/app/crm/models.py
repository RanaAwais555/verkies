"""CRM core for Phase 1: leads, opportunities, tasks, activities and the account timeline.

Deals, projects and campaigns arrive in later phases; their foreign keys are added with them.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    ActivityChannel,
    LeadStatus,
    PriorityBand,
    RejectionReason,
    TaskPriority,
    TaskStatus,
)
from app.core.models import (
    Base,
    CreatedMixin,
    IdMixin,
    Score,
    SoftDeleteMixin,
    TimestampMixin,
    score,
    score_checks,
    text_enum,
)


class Lead(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        # One lead per research run, so a run can never be approved twice.
        Index(
            "uq_leads_research_run",
            "research_run_id",
            unique=True,
            postgresql_where=text("research_run_id IS NOT NULL"),
        ),
        *score_checks("priority_score"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    research_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_runs.id"))
    source: Mapped[str] = mapped_column(String(80))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[LeadStatus] = mapped_column(
        text_enum(LeadStatus), default=LeadStatus.NEW, index=True
    )
    # The snapshot holds all ten scores; priority is copied for sorting the queue.
    score_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("score_snapshots.id"))
    priority_score: Score = score()
    priority_band: Mapped[PriorityBand | None] = mapped_column(text_enum(PriorityBand))
    qualified_at: Mapped[datetime | None]
    rejection_reason: Mapped[RejectionReason | None] = mapped_column(text_enum(RejectionReason))
    rejection_note: Mapped[str | None] = mapped_column(Text)


class Opportunity(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(
            "probability IS NULL OR (probability >= 0 AND probability <= 100)",
            name="probability_range",
        ),
        CheckConstraint(
            "estimated_value IS NULL OR estimated_value >= 0", name="estimated_value_positive"
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    problem: Mapped[str] = mapped_column(Text)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunity_categories.id"))
    service_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("services.id"))
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    expected_close: Mapped[date | None]
    stage: Mapped[str] = mapped_column(String(60), default="qualified_opportunity")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    # Every active opportunity needs a next action with owner and due date (§12).
    next_action_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", use_alter=True)
    )


class Task(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index(
            "ix_tasks_owner_open_due",
            "owner_id",
            "due_at",
            postgresql_where=text("status = 'open'"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    due_at: Mapped[datetime | None]
    priority: Mapped[TaskPriority] = mapped_column(
        text_enum(TaskPriority), default=TaskPriority.NORMAL
    )
    status: Mapped[TaskStatus] = mapped_column(text_enum(TaskStatus), default=TaskStatus.OPEN)
    recurrence: Mapped[str | None] = mapped_column(String(120))
    completed_at: Mapped[datetime | None]


class Activity(IdMixin, CreatedMixin, Base):
    __tablename__ = "activities"

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    channel: Mapped[ActivityChannel] = mapped_column(text_enum(ActivityChannel))
    activity_type: Mapped[str] = mapped_column(String(60))
    occurred_at: Mapped[datetime]
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class TimelineEvent(IdMixin, Base):
    """Append-only read model of everything that happened to an account (§12)."""

    __tablename__ = "timeline_events"
    __table_args__ = (Index("ix_timeline_events_account_time", "account_id", "occurred_at"),)

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    event_type: Mapped[str] = mapped_column(String(60))
    ref_table: Mapped[str | None] = mapped_column(String(64))
    ref_id: Mapped[uuid.UUID | None]
    summary: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
