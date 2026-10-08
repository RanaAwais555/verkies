"""Evidence and claims (§3 evidence first, AI_SPEC.md §2).

All four tables are append-only (trigger). A fact or inference claim must cite at least one
evidence row by the end of its transaction (deferred constraint trigger, see the migration).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, ForeignKey, Numeric, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ClaimClass, EvidenceType
from app.core.models import Base, CreatedMixin, IdMixin, confidence_check, text_enum

claim_evidence = Table(
    "claim_evidence",
    Base.metadata,
    Column("claim_id", ForeignKey("claims.id"), primary_key=True),
    Column("evidence_id", ForeignKey("evidence.id"), primary_key=True, index=True),
)

# A recommendation rests on the facts and inferences it cites.
claim_support = Table(
    "claim_support",
    Base.metadata,
    Column("claim_id", ForeignKey("claims.id"), primary_key=True),
    Column("supported_by_claim_id", ForeignKey("claims.id"), primary_key=True),
)


class Evidence(IdMixin, CreatedMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (confidence_check(),)

    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    research_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_runs.id"), index=True
    )
    source_url: Mapped[str] = mapped_column(Text)
    source_domain: Mapped[str] = mapped_column(String(253), index=True)
    collected_at: Mapped[datetime]
    published_at: Mapped[datetime | None]
    evidence_type: Mapped[EvidenceType] = mapped_column(text_enum(EvidenceType))
    evidence_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    raw_response_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("raw_responses.id"))


class Claim(IdMixin, CreatedMixin, Base):
    __tablename__ = "claims"
    __table_args__ = (confidence_check(),)

    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    research_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_runs.id"), index=True
    )
    claim_class: Mapped[ClaimClass] = mapped_column(text_enum(ClaimClass))
    # Dotted topic, e.g. "conversion.primary_cta".
    subject: Mapped[str] = mapped_column(String(120))
    statement: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2))
