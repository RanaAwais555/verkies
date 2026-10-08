"""Writes timeline events in the caller's transaction, at the moment something happens (§12)."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crm.models import TimelineEvent


def add(
    db: AsyncSession,
    *,
    account_id: uuid.UUID,
    event_type: str,
    summary: str,
    actor_id: uuid.UUID | None,
    ref_table: str | None = None,
    ref_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
) -> TimelineEvent:
    event = TimelineEvent(
        account_id=account_id,
        event_type=event_type,
        summary=summary,
        actor_id=actor_id,
        ref_table=ref_table,
        ref_id=ref_id,
    )
    if occurred_at is not None:
        event.occurred_at = occurred_at
    db.add(event)
    return event
