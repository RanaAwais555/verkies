"""Versioned ICP configuration and per-run qualification results (ICP_SPEC.md)."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import RejectionReason
from app.core.models import (
    Base,
    CreatedMixin,
    IdMixin,
    Score,
    score,
    score_checks,
    text_enum,
)


class IcpConfig(IdMixin, CreatedMixin, Base):
    __tablename__ = "icp_configs"
    __table_args__ = (
        Index(
            "uq_icp_configs_single_active",
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


class QualificationResult(IdMixin, CreatedMixin, Base):
    __tablename__ = "qualification_results"
    __table_args__ = score_checks("icp_fit")

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), unique=True
    )
    icp_config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("icp_configs.id"))
    icp_fit: Score = score()
    components: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    negative_icp_hits: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    hard_reject: Mapped[bool] = mapped_column(default=False)
    rejection_reason: Mapped[RejectionReason | None] = mapped_column(text_enum(RejectionReason))
    explanation: Mapped[str] = mapped_column(Text, default="")
