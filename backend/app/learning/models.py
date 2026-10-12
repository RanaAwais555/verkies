"""What the learning engine learns from (master context §13 won-deal data, §15; slice 5.1).

Salesperson feedback is what people said about a lead. Deal outcomes are what was true about an
account and its deal at the moment the deal was won or lost, kept as written so later changes to
the account (new research, new scores) never rewrite history.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import FeedbackKind, LostReason, StageOutcome
from app.core.models import Base, CreatedMixin, IdMixin, text_enum


class SalesFeedback(IdMixin, CreatedMixin, Base):
    """One piece of §15 feedback on an account, and the lead or opportunity it was about."""

    __tablename__ = "sales_feedback"

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    kind: Mapped[FeedbackKind] = mapped_column(text_enum(FeedbackKind), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    given_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class DealOutcome(IdMixin, Base):
    """A won or lost deal and what was true when it closed. A deal reopened and closed again gets
    a new row; the old one is marked superseded, never changed otherwise."""

    __tablename__ = "deal_outcomes"
    __table_args__ = (
        Index(
            "uq_deal_outcomes_current",
            "deal_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )

    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    outcome: Mapped[StageOutcome] = mapped_column(text_enum(StageOutcome))
    lost_reason: Mapped[LostReason | None] = mapped_column(text_enum(LostReason))
    closed_at: Mapped[datetime]
    # Recorded after the fact (deals closed before slice 5.1): the facts are as of the capture,
    # not the close, and analysis can tell them apart.
    captured_late: Mapped[bool] = mapped_column(default=False)
    recorded_at: Mapped[datetime] = mapped_column(server_default=func.now())
    superseded_at: Mapped[datetime | None]

    pipeline_key: Mapped[str] = mapped_column(String(60))
    value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    service_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("services.id"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunity_categories.id"))
    industry: Mapped[str | None] = mapped_column(String(120))
    company_size_band: Mapped[str | None] = mapped_column(String(40))
    hq_country: Mapped[str | None] = mapped_column(String(2))
    source: Mapped[str | None] = mapped_column(String(80))
    # The decision-maker role of the person the deal was worked with most; None is Unknown.
    buyer_role: Mapped[str | None] = mapped_column(String(40))
    # Days from the deal being opened, and from the lead being qualified, to the close.
    deal_days: Mapped[int] = mapped_column(Integer)
    lead_days: Mapped[int | None] = mapped_column(Integer)
    # Dated buying signals seen in the 180 days before the close: [{signal, at, evidence_id}].
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # The ten dimensions and priority, from the first score snapshot (when the lead was
    # qualified) and the latest one before the close; null values are Unknown.
    first_scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    close_scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # The most similar Verkies reference project from the latest research, if any.
    reference_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reference_projects.id")
    )
