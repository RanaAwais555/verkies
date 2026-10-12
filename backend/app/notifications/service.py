"""In-app notifications (master context §13 Notifications; slice 6.3).

A notification is a line in the app for one person; it is never emailed or sent anywhere. Each
person can switch a kind off (users.notifications_off); a kind switched off is not created.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.errors import NotFound, ValidationFailed
from app.notifications.models import Notification

KINDS = {
    "monitoring_alert": "Monitoring found something new on an account you watch",
    "rule_task": "An alert rule gave you a follow-up task",
}


async def notify(
    db: AsyncSession,
    user_ids: set[uuid.UUID],
    *,
    kind: str,
    title: str,
    body: str | None = None,
    account_id: uuid.UUID | None = None,
    link: str | None = None,
) -> int:
    """Add a notification for each active person who has not switched this kind off."""
    if not user_ids:
        return 0
    users = (
        await db.execute(select(User).where(User.id.in_(user_ids), User.is_active.is_(True)))
    ).scalars()
    added = 0
    for user in users:
        if kind in (user.notifications_off or []):
            continue
        db.add(
            Notification(
                user_id=user.id,
                kind=kind,
                title=title[:300],
                body=body,
                account_id=account_id,
                link=link,
            )
        )
        added += 1
    return added


async def listing(
    db: AsyncSession, user: User, *, unread_only: bool = False, limit: int = 50
) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id).limit(limit)
    return list((await db.execute(stmt)).scalars())


async def unread_count(db: AsyncSession, user: User) -> int:
    return (
        await db.execute(
            select(func.count()).where(
                Notification.user_id == user.id, Notification.read_at.is_(None)
            )
        )
    ).scalar_one()


async def mark_read(db: AsyncSession, user: User, notification_id: uuid.UUID) -> Notification:
    row = await db.get(Notification, notification_id)
    if row is None or row.user_id != user.id:
        raise NotFound("Notification not found.")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        await db.commit()
    return row


async def mark_all_read(db: AsyncSession, user: User) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()


async def set_preferences(db: AsyncSession, user: User, off: list[str]) -> list[str]:
    unknown = sorted(set(off) - KINDS.keys())
    if unknown:
        raise ValidationFailed(f"Unknown notification kind: {', '.join(unknown)}.")
    user.notifications_off = sorted(set(off))
    await db.commit()
    return user.notifications_off
