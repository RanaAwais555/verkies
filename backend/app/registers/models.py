"""Regulators' registers kept in VROS (slice 8.1): one row per source with how its last refresh
went, and one row per organisation the source lists.

A register record is not an Account and not a discovery candidate. It is VROS's copy of what the
regulator publishes, refreshed on the source's own schedule, and searched to start discovery
jobs. Organisations that leave the register keep their row with `removed_at` set, so a later
change can be told apart from a first sighting.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import RegisterRefreshStatus
from app.core.models import Base, IdMixin, TimestampMixin, text_enum


class RegisterSource(TimestampMixin, Base):
    """How a source's last refresh went. Created on its first refresh."""

    __tablename__ = "register_sources"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_checked_at: Mapped[datetime | None]
    # When the published copy last differed from the one kept (an applied refresh).
    last_changed_at: Mapped[datetime | None]
    last_status: Mapped[RegisterRefreshStatus | None] = mapped_column(
        text_enum(RegisterRefreshStatus)
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    # SHA-256 of the last applied content (entries in a fixed order): the same content in a
    # later download is not applied again.
    content_hash: Mapped[str | None] = mapped_column(String(64))
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    active_count: Mapped[int] = mapped_column(Integer, default=0)
    # What the last applied refresh changed: {"new": n, "updated": n, "removed": n}.
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class RegisterRecord(IdMixin, TimestampMixin, Base):
    """One organisation as a register lists it."""

    __tablename__ = "register_records"
    __table_args__ = (
        UniqueConstraint("source", "source_id"),
        Index("ix_register_records_source_active", "source", "active"),
    )

    source: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(80))  # e.g. the SRA number
    name: Mapped[str] = mapped_column(String(300))
    # Authorised (or licensed) now, by the register's own status.
    active: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str | None] = mapped_column(String(80))
    legal_form: Mapped[str | None] = mapped_column(String(80))
    company_number: Mapped[str | None] = mapped_column(String(8), index=True)
    website: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(320))
    postcode: Mapped[str | None] = mapped_column(String(12))  # head office
    town: Mapped[str | None] = mapped_column(String(120))
    # Postcode areas of every office ("SE", "EC", "M"...), for location filters.
    postcode_areas: Mapped[list[str]] = mapped_column(ARRAY(String(2)), default=list)
    # The register's own categories, e.g. the SRA's areas of work.
    areas: Mapped[list[str]] = mapped_column(ARRAY(String(120)), default=list)
    office_count: Mapped[int | None] = mapped_column(Integer)
    authorised_on: Mapped[date | None]
    # Latest annual income in pounds, where the register states it (charities). Slice 8.3.
    income: Mapped[int | None] = mapped_column(BigInteger)
    # SHA-256 of this entry as last applied: a refresh rewrites only rows that changed.
    row_hash: Mapped[str | None] = mapped_column(String(64))
    first_seen_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    removed_at: Mapped[datetime | None]
    # Anything else worth keeping from the source (trading names, other offices).
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
