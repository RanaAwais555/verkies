"""Opportunity categories (§9) and the candidates detectors find in a research run."""

import uuid
from decimal import Decimal

from sqlalchemy import Column, ForeignKey, Numeric, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, CreatedMixin, IdMixin, TimestampMixin, confidence_check

opportunity_candidate_evidence = Table(
    "opportunity_candidate_evidence",
    Base.metadata,
    Column(
        "candidate_id",
        ForeignKey("opportunity_candidates.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("evidence_id", ForeignKey("evidence.id"), primary_key=True),
)


class OpportunityCategory(IdMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_categories"

    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(default=True)


class OpportunityCandidate(IdMixin, CreatedMixin, Base):
    __tablename__ = "opportunity_candidates"
    __table_args__ = (confidence_check(),)

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunity_categories.id"))
    title: Mapped[str] = mapped_column(String(200))
    problem_statement: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    # Which detector rule produced it, for explanation and tuning.
    rule_key: Mapped[str] = mapped_column(String(80))
