"""The Account (permanent central entity, §6), its domains, identifiers, contacts, suppressions."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    AccountType,
    AgencyClass,
    DecisionMakerRole,
    LinkedInConnectionStatus,
    PriorityBand,
    SuppressionKind,
    VerificationStatus,
)
from app.core.models import (
    SCORE_COLUMNS,
    Base,
    CreatedMixin,
    IdMixin,
    Score,
    SoftDeleteMixin,
    TimestampMixin,
    confidence_check,
    score,
    score_checks,
    text_enum,
)


class Account(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        # One live account per domain; a soft-deleted account frees its domain.
        Index(
            "uq_accounts_primary_domain_live",
            "primary_domain",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_accounts_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index("ix_accounts_priority_score", "priority_score", postgresql_using="btree"),
        CheckConstraint("hq_country IS NULL OR hq_country ~ '^[A-Z]{2}$'", name="hq_country_iso2"),
        *score_checks(*SCORE_COLUMNS, "priority_score"),
    )

    name: Mapped[str] = mapped_column(String(300))
    legal_name: Mapped[str | None] = mapped_column(String(300))
    primary_domain: Mapped[str | None] = mapped_column(String(253))
    website_url: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String(120))
    sub_industry: Mapped[str | None] = mapped_column(String(120))
    business_model: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    hq_city: Mapped[str | None] = mapped_column(String(120))
    hq_country: Mapped[str | None] = mapped_column(String(2))
    company_size_band: Mapped[str | None] = mapped_column(String(40))
    # Only when verified (§3 no hallucinations).
    estimated_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    estimated_revenue_currency: Mapped[str | None] = mapped_column(String(3))
    account_type: Mapped[AccountType] = mapped_column(
        text_enum(AccountType), default=AccountType.PROSPECT, index=True
    )
    agency_class: Mapped[AgencyClass | None] = mapped_column(text_enum(AgencyClass))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str | None] = mapped_column(String(80))

    # Cached copies of the latest score snapshot; score_snapshots is the source of truth.
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

    last_activity_at: Mapped[datetime | None]
    next_activity_at: Mapped[datetime | None]

    linkedin_company_url: Mapped[str | None] = mapped_column(Text)
    linkedin_employee_range: Mapped[str | None] = mapped_column(String(40))
    linkedin_employee_range_at: Mapped[datetime | None]


class AccountDomain(IdMixin, CreatedMixin, Base):
    __tablename__ = "account_domains"
    __table_args__ = (
        Index(
            "ix_account_domains_domain_trgm",
            "domain",
            postgresql_using="gin",
            postgresql_ops={"domain": "gin_trgm_ops"},
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    domain: Mapped[str] = mapped_column(String(253), unique=True)
    is_primary: Mapped[bool] = mapped_column(default=False)


class AccountIdentifier(IdMixin, CreatedMixin, Base):
    __tablename__ = "account_identifiers"
    __table_args__ = (UniqueConstraint("scheme", "value"),)

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    scheme: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(String(120))


class Contact(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A person at an Account. Stored only from public, attributable sources (SECURITY.md §6)."""

    __tablename__ = "contacts"
    __table_args__ = (confidence_check(),)

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    profile_url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(80))
    source_url: Mapped[str | None] = mapped_column(Text)
    collected_at: Mapped[datetime]
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    decision_maker_role: Mapped[DecisionMakerRole | None] = mapped_column(
        text_enum(DecisionMakerRole)
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        text_enum(VerificationStatus), default=VerificationStatus.UNVERIFIED
    )
    lawful_basis: Mapped[str] = mapped_column(String(80), default="b2b_legitimate_interest")
    notes: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    linkedin_connection_status: Mapped[LinkedInConnectionStatus | None] = mapped_column(
        text_enum(LinkedInConnectionStatus)
    )


class Suppression(IdMixin, Base):
    """Never contact or re-add these (§12B, SECURITY.md §6)."""

    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("kind", "value"),)

    kind: Mapped[SuppressionKind] = mapped_column(text_enum(SuppressionKind))
    value: Mapped[str] = mapped_column(String(320))
    reason: Mapped[str] = mapped_column(Text)
    added_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
