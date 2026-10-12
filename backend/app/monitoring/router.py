"""/monitoring and /accounts/{id}/watch: watchlists, monitoring checks and alerts (slice 6.1)."""

import uuid
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.core.errors import AppError
from app.leads.ranking import SIGNAL_LABELS
from app.monitoring import service
from app.monitoring.models import MonitorAlert

router = APIRouter(tags=["monitoring"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]


class QueueUnavailable(AppError):
    status_code = 503
    code = "queue_unavailable"


def enqueue_check(account_id: uuid.UUID, user_id: uuid.UUID) -> None:
    from app.workers.celery_app import celery_app

    celery_app.send_task("vros.monitoring.check_account", args=[str(account_id), str(user_id)])


def get_check_enqueuer() -> Callable[[uuid.UUID, uuid.UUID], None]:
    return enqueue_check


CheckEnqueuer = Annotated[Callable[[uuid.UUID, uuid.UUID], None], Depends(get_check_enqueuer)]


class WatchedOut(BaseModel):
    account_id: uuid.UUID
    name: str
    primary_domain: str | None
    account_type: str
    watchers: int
    watching: bool
    last_checked_at: datetime | None
    open_alerts: int


class AlertOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    account_name: str
    kind: str
    signal: str | None
    signal_label: str | None
    title: str
    source_url: str
    happened_on: date | None
    created_at: datetime
    reviewed: bool

    @classmethod
    def of(cls, a: MonitorAlert, account_name: str) -> "AlertOut":
        return cls(
            id=a.id,
            account_id=a.account_id,
            account_name=account_name,
            kind=a.kind,
            signal=a.signal,
            signal_label=SIGNAL_LABELS.get(a.signal) if a.signal else None,
            title=a.title,
            source_url=a.source_url,
            happened_on=a.happened_on,
            created_at=a.created_at,
            reviewed=a.reviewed_at is not None,
        )


@router.put("/accounts/{account_id}/watch", status_code=204)
async def watch(account_id: uuid.UUID, user: Member, db: DbSession) -> Response:
    await service.watch(db, user=user, account_id=account_id)
    return Response(status_code=204)


@router.delete("/accounts/{account_id}/watch", status_code=204)
async def unwatch(account_id: uuid.UUID, user: Member, db: DbSession) -> Response:
    await service.unwatch(db, user=user, account_id=account_id)
    return Response(status_code=204)


@router.post("/accounts/{account_id}/monitor/check", status_code=202)
async def check_now(
    account_id: uuid.UUID, user: Member, db: DbSession, enqueue: CheckEnqueuer
) -> dict[str, str]:
    """Check the account's sources now instead of waiting for the daily check."""
    await service.visible_account(db, user, account_id)
    try:
        enqueue(account_id, user.id)
    except Exception as exc:
        raise QueueUnavailable("The background worker is unavailable. Try again shortly.") from exc
    return {"status": "queued"}


@router.get("/monitoring/watched")
async def watched(user: Member, db: DbSession, mine: bool = True) -> list[WatchedOut]:
    views = await service.watched(db, user=user, mine=mine)
    return [
        WatchedOut(
            account_id=v.account.id,
            name=v.account.name,
            primary_domain=v.account.primary_domain,
            account_type=v.account.account_type.value,
            watchers=v.watchers,
            watching=v.watching,
            last_checked_at=v.last_checked_at,
            open_alerts=v.open_alerts,
        )
        for v in views
    ]


@router.get("/monitoring/alerts")
async def alerts(
    user: Member,
    db: DbSession,
    account_id: uuid.UUID | None = None,
    open: bool = False,
    mine: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[AlertOut]:
    rows = await service.alerts(
        db, user=user, account_id=account_id, open_only=open, mine=mine, limit=limit
    )
    return [AlertOut.of(a, acc.name) for a, acc in rows]


@router.post("/monitoring/alerts/{alert_id}/review")
async def review(alert_id: uuid.UUID, user: Member, db: DbSession) -> AlertOut:
    alert = await service.review_alert(db, user=user, alert_id=alert_id)
    account = await service.visible_account(db, user, alert.account_id)
    return AlertOut.of(alert, account.name)
