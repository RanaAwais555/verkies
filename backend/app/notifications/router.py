"""/notifications: a person's in-app notifications and which kinds they want (slice 6.3)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.auth.deps import CurrentUser, DbSession
from app.notifications import service
from app.notifications.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    account_id: uuid.UUID | None
    link: str | None
    created_at: datetime
    read: bool

    @classmethod
    def of(cls, n: Notification) -> "NotificationOut":
        return cls(
            id=n.id,
            kind=n.kind,
            title=n.title,
            body=n.body,
            account_id=n.account_id,
            link=n.link,
            created_at=n.created_at,
            read=n.read_at is not None,
        )


class CountOut(BaseModel):
    unread: int


class KindOut(BaseModel):
    kind: str
    label: str
    on: bool


class PreferencesIn(BaseModel):
    off: list[str]


@router.get("")
async def list_notifications(
    user: CurrentUser, db: DbSession, unread: bool = False
) -> list[NotificationOut]:
    return [NotificationOut.of(n) for n in await service.listing(db, user, unread_only=unread)]


@router.get("/count")
async def count(user: CurrentUser, db: DbSession) -> CountOut:
    return CountOut(unread=await service.unread_count(db, user))


@router.post("/{notification_id}/read")
async def read(notification_id: uuid.UUID, user: CurrentUser, db: DbSession) -> NotificationOut:
    return NotificationOut.of(await service.mark_read(db, user, notification_id))


@router.post("/read-all", status_code=204)
async def read_all(user: CurrentUser, db: DbSession) -> Response:
    await service.mark_all_read(db, user)
    return Response(status_code=204)


def _kinds(off: list[str]) -> list[KindOut]:
    return [KindOut(kind=k, label=label, on=k not in off) for k, label in service.KINDS.items()]


@router.get("/preferences")
async def preferences(user: CurrentUser) -> list[KindOut]:
    return _kinds(user.notifications_off or [])


@router.put("/preferences")
async def set_preferences(body: PreferencesIn, user: CurrentUser, db: DbSession) -> list[KindOut]:
    return _kinds(await service.set_preferences(db, user, body.off))
