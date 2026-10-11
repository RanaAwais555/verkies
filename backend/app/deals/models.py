"""Pipelines, their stages, deals and each deal's stage history (master context §12, §13).

Pipelines and stages are configuration (seeded with the §12 defaults in migration 0014), so a
team can rename stages or change default probabilities without a code change.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import LostReason, PipelineKind, StageOutcome
from app.core.models import Base, CreatedMixin, IdMixin, SoftDeleteMixin, TimestampMixin, text_enum


class Pipeline(IdMixin, CreatedMixin, Base):
    __tablename__ = "pipelines"

    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[PipelineKind] = mapped_column(text_enum(PipelineKind))
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class PipelineStage(IdMixin, CreatedMixin, Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "key"),
        CheckConstraint(
            "probability IS NULL OR (probability >= 0 AND probability <= 100)",
            name="probability_range",
        ),
    )

    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id"), index=True)
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(SmallInteger)
    # Default chance of winning a deal at this stage, 0-100. NULL: no revenue to weight
    # (partnerships), so the deal is left out of the weighted forecast rather than counted as 0.
    probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    outcome: Mapped[StageOutcome] = mapped_column(
        text_enum(StageOutcome), default=StageOutcome.OPEN
    )


class Deal(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "deals"
    __table_args__ = (
        CheckConstraint("value IS NULL OR value >= 0", name="value_not_negative"),
        CheckConstraint(
            "probability IS NULL OR (probability >= 0 AND probability <= 100)",
            name="probability_range",
        ),
        CheckConstraint("outcome <> 'lost' OR lost_reason IS NOT NULL", name="lost_needs_reason"),
        # One live deal per opportunity: the deal is how the opportunity is worked.
        Index(
            "uq_deals_opportunity_live",
            "opportunity_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND opportunity_id IS NOT NULL"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id"), index=True)
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_stages.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # Entered by a person; VROS never estimates a deal's value. NULL is Unknown.
    value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    # Overrides the stage's default probability when someone sets it.
    probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    expected_close: Mapped[date | None]
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    # Copied from the stage on every move, so lists can filter without a join.
    outcome: Mapped[StageOutcome] = mapped_column(
        text_enum(StageOutcome), default=StageOutcome.OPEN
    )
    stage_entered_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[datetime | None]
    lost_reason: Mapped[LostReason | None] = mapped_column(text_enum(LostReason))
    lost_note: Mapped[str | None] = mapped_column(Text)


class DealStageChange(IdMixin, Base):
    """Every stage a deal passed through and when: days in stage and the conversion funnel."""

    __tablename__ = "deal_stage_changes"

    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"), index=True)
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pipeline_stages.id"))
    to_stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_stages.id"))
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
