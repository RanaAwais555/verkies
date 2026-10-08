"""/audit: read the audit log, newest first, with keyset pagination."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, tuple_

from app.audit.models import AuditLog
from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.core.errors import ValidationFailed

router = APIRouter(prefix="/audit", tags=["audit"])

Auditor = Annotated[User, Depends(require_permission("audit.read"))]


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    user_id: uuid.UUID | None
    object_table: str
    object_id: uuid.UUID | None
    action: str
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    source: str
    reason: str | None


class AuditPage(BaseModel):
    items: list[AuditEntryOut]
    # Pass as `before` to get the next (older) page; null on the last page.
    next_cursor: str | None


def _cursor(entry: AuditLog) -> str:
    return f"{entry.occurred_at.isoformat()}|{entry.id}"


def _parse_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    stamp, _, raw_id = cursor.partition("|")
    try:
        return datetime.fromisoformat(stamp), uuid.UUID(raw_id)
    except ValueError:
        raise ValidationFailed("Invalid cursor.") from None


@router.get("")
async def list_audit(
    _: Auditor,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: str | None = None,
    object_table: str | None = None,
    object_id: uuid.UUID | None = None,
) -> AuditPage:
    query = select(AuditLog).order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
    if before:
        stamp, raw_id = _parse_cursor(before)
        query = query.where(tuple_(AuditLog.occurred_at, AuditLog.id) < tuple_(stamp, raw_id))
    if object_table:
        query = query.where(AuditLog.object_table == object_table)
    if object_id:
        query = query.where(AuditLog.object_id == object_id)
    rows = list((await db.execute(query.limit(limit + 1))).scalars())
    page, more = rows[:limit], len(rows) > limit
    return AuditPage(
        items=[AuditEntryOut.model_validate(r, from_attributes=True) for r in page],
        next_cursor=_cursor(page[-1]) if more else None,
    )
