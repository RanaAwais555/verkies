"""Projects, their milestones and risks: lightweight delivery tracking after a deal is won
(master context §6, §14; slice 4.1). VROS does not try to replace a project tool."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ProjectStatus, RiskSeverity
from app.core.models import Base, IdMixin, SoftDeleteMixin, TimestampMixin, text_enum


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
