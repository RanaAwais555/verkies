"""Declarative base, column helpers and mixins shared by every table (DATA_MODEL.md §1)."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, MetaData, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SCORE_COLUMNS = (
    "icp_score",
    "opportunity_score",
    "intent_score",
    "buyer_confidence",
    "data_confidence",
    "service_fit",
    "timing_score",
    "commercial_potential",
    "client_similarity",
    "evidence_strength",
)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012 - SQLAlchemy reads this class attribute
        datetime: DateTime(timezone=True),
        uuid.UUID: UUID(as_uuid=True),
    }


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class CreatedMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TimestampMixin(CreatedMixin):
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None]


def text_enum(enum_cls: type[StrEnum], name: str | None = None) -> Enum:
    """Store a StrEnum as text guarded by a CHECK constraint (no native PG enum to migrate)."""
    return Enum(
        enum_cls,
        name=name or enum_cls.__name__.lower(),
        native_enum=False,
        create_constraint=True,
        length=40,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


def score() -> Any:
    """A 0-100 score. NULL means Unknown, never zero (SCORING_SPEC.md §1)."""
    return mapped_column(Numeric(5, 2), nullable=True)


def score_checks(*columns: str) -> tuple[CheckConstraint, ...]:
    return tuple(
        CheckConstraint(f"{col} IS NULL OR ({col} >= 0 AND {col} <= 100)", name=f"{col}_range")
        for col in columns
    )


def confidence_check(column: str = "confidence") -> CheckConstraint:
    return CheckConstraint(f"{column} >= 0 AND {column} <= 1", name=f"{column}_range")


Score = Mapped[Decimal | None]
