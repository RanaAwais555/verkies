"""Research runs, their stages (progress), and cached raw fetches (ARCHITECTURE.md §5)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    JobStatus,
    PageKind,
    RejectionReason,
    ResearchStageName,
    ReviewStatus,
)
from app.core.models import Base, CreatedMixin, IdMixin, TimestampMixin, text_enum


class ResearchRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "research_runs"

    input_url: Mapped[str] = mapped_column(Text)
    normalised_domain: Mapped[str] = mapped_column(String(253), index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[JobStatus] = mapped_column(
        text_enum(JobStatus), default=JobStatus.QUEUED, index=True
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        text_enum(ReviewStatus), default=ReviewStatus.PENDING, index=True
    )
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    error: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(default=0)
    crawl_budget: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Account IDs that may be the same company (DATA_MODEL.md §3); the reviewer decides.
    possible_duplicate_of: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None]
    rejection_reason: Mapped[RejectionReason | None] = mapped_column(text_enum(RejectionReason))
    rejection_note: Mapped[str | None] = mapped_column(Text)


class ResearchStage(IdMixin, TimestampMixin, Base):
    __tablename__ = "research_stages"
    __table_args__ = (
        UniqueConstraint("research_run_id", "stage"),
        CheckConstraint("progress_pct BETWEEN 0 AND 100", name="progress_pct_range"),
    )

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[ResearchStageName] = mapped_column(text_enum(ResearchStageName))
    status: Mapped[JobStatus] = mapped_column(text_enum(JobStatus), default=JobStatus.QUEUED)
    progress_pct: Mapped[int] = mapped_column(SmallInteger, default=0)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class RawResponse(IdMixin, Base):
    """A cached fetch. The body lives in storage under body_ref (PROVIDER_SPEC.md §1).
    A rendered page (JavaScript executed) is cached separately from its static HTML."""

    __tablename__ = "raw_responses"
    __table_args__ = (UniqueConstraint("url", "rendered", "content_hash"),)

    url: Mapped[str] = mapped_column(Text, index=True)
    final_url: Mapped[str] = mapped_column(Text)
    rendered: Mapped[bool] = mapped_column(default=False)
    fetched_at: Mapped[datetime] = mapped_column(server_default=func.now())
    status_code: Mapped[int] = mapped_column(SmallInteger)
    headers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    body_ref: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(200))
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    content_hash: Mapped[str] = mapped_column(String(64))


class ResearchPage(IdMixin, CreatedMixin, Base):
    """What a run fetched, skipped or was refused, and why. Analysis reads pages from here."""

    __tablename__ = "research_pages"

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[PageKind] = mapped_column(text_enum(PageKind))
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    # Why it was chosen: start, link, sitemap, robots.
    discovered_via: Mapped[str] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(40))
    status_code: Mapped[int | None] = mapped_column(SmallInteger)
    content_type: Mapped[str | None] = mapped_column(String(200))
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    raw_response_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("raw_responses.id"))
    from_cache: Mapped[bool] = mapped_column(default=False)
    rendered: Mapped[bool] = mapped_column(default=False)
    title: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    duplicate_of_url: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None]
    # Set when nothing usable was fetched: robots_disallowed, fetch_blocked:<code>, ...
    skip_reason: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(Text)
