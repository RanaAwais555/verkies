"""Versioned scoring configuration and append-only score snapshots (SCORING_SPEC.md)."""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import PriorityBand
from app.core.models import (
    SCORE_COLUMNS,
    Base,
    CreatedMixin,
    IdMixin,
    Score,
    score,
    score_checks,
    text_enum,
)


class ScoringConfig(IdMixin, CreatedMixin, Base):
    __tablename__ = "scoring_configs"
    __table_args__ = (
        Index(
            "uq_scoring_configs_single_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    version: Mapped[int] = mapped_column(unique=True)
    is_active: Mapped[bool] = mapped_column(default=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ScoreSnapshot(IdMixin, CreatedMixin, Base):
    __tablename__ = "score_snapshots"
    __table_args__ = (
        CheckConstraint(
            "research_run_id IS NOT NULL OR account_id IS NOT NULL", name="has_subject"
        ),
        *score_checks(*SCORE_COLUMNS, "priority_score"),
    )

    research_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_runs.id"), index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    scoring_config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scoring_configs.id"))

    icp_score: Score = score()
    opportunity_score: Score = score()
    intent_score: Score = score()
    buyer_confidence: Score = score()
    data_confidence: Score = score()
    service_fit: Score = score()
    timing_score: Score = score()
    commercial_potential: Score = score()
    client_similarity: Score = score()
    evidence_strength: Score = score()
    priority_score: Score = score()
    priority_band: Mapped[PriorityBand | None] = mapped_column(text_enum(PriorityBand))
    qualifies: Mapped[bool] = mapped_column(default=False)
    # Per dimension: inputs, evidence IDs, weight, contribution, Unknown inputs; gates applied.
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
