"""Append-only audit log (SECURITY.md §5). UPDATE and DELETE are blocked by a trigger."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AuditSource
from app.core.models import Base, IdMixin, text_enum


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_object", "object_table", "object_id"),)

    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    object_table: Mapped[str] = mapped_column(String(64))
    object_id: Mapped[uuid.UUID | None]
    action: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source: Mapped[AuditSource] = mapped_column(text_enum(AuditSource))
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))
