"""Discovery (§15): jobs that bring in candidate companies, and the candidates themselves.

A candidate is not an Account. It becomes one only through research and a person's approval.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import CandidateStatus, DiscoveryKind, DiscoveryStatus
from app.core.models import Base, CreatedMixin, IdMixin, TimestampMixin, text_enum


class DiscoveryJob(IdMixin, TimestampMixin, Base):
    __tablename__ = "discovery_jobs"

    kind: Mapped[DiscoveryKind] = mapped_column(text_enum(DiscoveryKind))
    name: Mapped[str] = mapped_column(String(200))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[DiscoveryStatus] = mapped_column(text_enum(DiscoveryStatus))
    # CSV: the header row, and which column feeds which field ({"website": "Web site", ...}).
    columns: Mapped[list[str]] = mapped_column(JSONB, default=list)
    mapping: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    # Counts per candidate status after the last check.
    stats: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)


class DiscoveredCompany(IdMixin, CreatedMixin, Base):
    __tablename__ = "discovered_companies"
    __table_args__ = (
        UniqueConstraint("discovery_job_id", "row_number"),
        Index("ix_discovered_companies_domain", "normalised_domain"),
    )

    discovery_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="CASCADE"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer)
    # The row exactly as uploaded, so a different mapping can be applied later.
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    name: Mapped[str | None] = mapped_column(String(300))
    website_url: Mapped[str | None] = mapped_column(Text)
    normalised_domain: Mapped[str | None] = mapped_column(String(253))
    country: Mapped[str | None] = mapped_column(String(120))
    industry: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CandidateStatus] = mapped_column(
        text_enum(CandidateStatus), default=CandidateStatus.PENDING, index=True
    )
    status_detail: Mapped[str | None] = mapped_column(Text)
    matched_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    research_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_runs.id"))
