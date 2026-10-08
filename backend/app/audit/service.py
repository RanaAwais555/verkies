"""Writes audit entries in the caller's transaction, so the entry commits with the change."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.core.enums import AuditSource
from app.core.logging import request_id_var


def record(
    db: AsyncSession,
    *,
    action: str,
    object_table: str,
    object_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    source: AuditSource,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    reason: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        object_table=object_table,
        object_id=object_id,
        user_id=user_id,
        source=source,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        request_id=request_id_var.get(),
    )
    db.add(entry)
    return entry
