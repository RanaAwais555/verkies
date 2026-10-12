"""Projects, their milestones and risks: lightweight delivery tracking after a deal is won
(master context §6, §14; slice 4.1). VROS does not try to replace a project tool. Client feedback
and the history of client health (slice 4.2)."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import HealthColour, ProjectStatus, RiskSeverity, Sentiment
from app.core.models import (
    Base,
    CreatedMixin,
    IdMixin,
    SoftDeleteMixin,
    TimestampMixin,
    text_enum,
)


class Project(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        # One live project per won deal; more work for the client is a new deal.
        Index(
            "uq_projects_deal_live",
            "deal_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND deal_id IS NOT NULL"),
        ),
        CheckConstraint(
            "target_date IS NULL OR start_date IS NULL OR target_date >= start_date",
            name="target_after_start",
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id"))
    name: Mapped[str] = mapped_column(String(200))
    service_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("services.id"))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[ProjectStatus] = mapped_column(
        text_enum(ProjectStatus), default=ProjectStatus.NOT_STARTED, index=True
    )
    start_date: Mapped[date | None]
    target_date: Mapped[date | None]
    # Set when the project is marked completed, cleared if it is reopened.
    completed_on: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)


class Milestone(IdMixin, TimestampMixin, Base):
    __tablename__ = "milestones"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date | None]
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    completed_at: Mapped[datetime | None]
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ProjectRisk(IdMixin, TimestampMixin, Base):
    """Something that could hurt delivery, raised by a person and open until resolved."""

    __tablename__ = "project_risks"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[RiskSeverity] = mapped_column(
        text_enum(RiskSeverity), default=RiskSeverity.MEDIUM
    )
    raised_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None]
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolution: Mapped[str | None] = mapped_column(Text)


class ClientFeedback(IdMixin, CreatedMixin, Base):
    """What a client said about working with Verkies, recorded by the person they said it to."""

    __tablename__ = "client_feedback"

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    sentiment: Mapped[Sentiment] = mapped_column(text_enum(Sentiment))
    note: Mapped[str | None] = mapped_column(Text)
    received_on: Mapped[date]
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ClientHealthSnapshot(IdMixin, Base):
    """A client's health each time it changed colour, with the reasons at that moment. The
    current health is always computed from the records; these rows are its history."""

    __tablename__ = "client_health_snapshots"

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    colour: Mapped[HealthColour] = mapped_column(text_enum(HealthColour))
    reasons: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    assessed_at: Mapped[datetime] = mapped_column(server_default=func.now())
