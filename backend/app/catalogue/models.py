"""Verkies service catalogue, reference projects and per-run service matches (§11)."""

import uuid
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, ForeignKey, Numeric, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ServiceSlot
from app.core.models import (
    Base,
    CreatedMixin,
    IdMixin,
    TimestampMixin,
    confidence_check,
    text_enum,
)

EMBEDDING_DIMENSIONS = 768  # nomic-embed-text (AI_SPEC.md §5)

reference_project_services = Table(
    "reference_project_services",
    Base.metadata,
    Column(
        "reference_project_id",
        ForeignKey("reference_projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("service_id", ForeignKey("services.id", ondelete="RESTRICT"), primary_key=True),
)


class Service(IdMixin, TimestampMixin, Base):
    __tablename__ = "services"

    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    # Opportunity category keys this service answers.
    solves: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source_url: Mapped[str | None] = mapped_column(Text)
    # Only confirmed services are ever recommended.
    confirmed: Mapped[bool] = mapped_column(default=False)
    parent_service_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("services.id"))
    is_active: Mapped[bool] = mapped_column(default=True)


class ReferenceProject(IdMixin, TimestampMixin, Base):
    """Previous Verkies work. Unknown fields stay NULL; similarity is Unknown until complete."""

    __tablename__ = "reference_projects"

    name: Mapped[str] = mapped_column(String(160), unique=True)
    industry: Mapped[str | None] = mapped_column(String(120))
    business_model: Mapped[str | None] = mapped_column(String(120))
    problem: Mapped[str | None] = mapped_column(Text)
    technologies: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    growth_stage: Mapped[str | None] = mapped_column(String(60))
    buyer_type: Mapped[str | None] = mapped_column(String(120))
    workflow_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(120))
    website_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    profile_complete: Mapped[bool] = mapped_column(default=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    services: Mapped[list[Service]] = relationship(
        secondary=reference_project_services, lazy="selectin"
    )


class ServiceMatch(IdMixin, CreatedMixin, Base):
    """At most three per run, one per slot (§11)."""

    __tablename__ = "service_matches"
    __table_args__ = (UniqueConstraint("research_run_id", "slot"), confidence_check())

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    slot: Mapped[ServiceSlot] = mapped_column(text_enum(ServiceSlot))
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id"))
    rationale: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2))
