"""/monitoring and /accounts/{id}/watch: watchlists, checks and alerts (slices 6.1 to 6.3)."""

import uuid
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.core.errors import AppError
from app.leads.ranking import SIGNAL_LABELS
from app.monitoring import rules, service
from app.monitoring.models import AlertRule, MonitorAlert

router = APIRouter(tags=["monitoring"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]
Admin = Annotated[User, Depends(require_permission("config.manage"))]
# Changes only the person's own things, so read access is enough (slice 7.4).
Personal = Annotated[
    User, Depends(require_permission("accounts.read", "accounts.read_own", personal=True))
]


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
    attention: str | None


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
    # A website change: change, topic, before, before_url, before_seen_at, after.
    detail: dict[str, Any] | None
    # Alert rules: the flag raised, the rules that matched, the task one created.
    raised: str | None
    rules: list[dict[str, Any]]
    task_id: uuid.UUID | None

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
            detail=a.detail,
            raised=a.raised,
            rules=a.rules or [],
            task_id=a.task_id,
        )


@router.put("/accounts/{account_id}/watch", status_code=204)
async def watch(account_id: uuid.UUID, user: Personal, db: DbSession) -> Response:
    await service.watch(db, user=user, account_id=account_id)
    return Response(status_code=204)


@router.delete("/accounts/{account_id}/watch", status_code=204)
async def unwatch(account_id: uuid.UUID, user: Personal, db: DbSession) -> Response:
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
async def watched(
    user: Member,
    db: DbSession,
    mine: bool = True,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[WatchedOut]:
    views = await service.watched(db, user=user, mine=mine, limit=limit)
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
            attention=v.attention,
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
    raised: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[AlertOut]:
    rows = await service.alerts(
        db,
        user=user,
        account_id=account_id,
        open_only=open,
        mine=mine,
        raised=raised,
        limit=limit,
    )
    return [AlertOut.of(a, acc.name) for a, acc in rows]


@router.post("/monitoring/alerts/{alert_id}/review")
async def review(alert_id: uuid.UUID, user: Member, db: DbSession) -> AlertOut:
    alert = await service.review_alert(db, user=user, alert_id=alert_id)
    account = await service.visible_account(db, user, alert.account_id)
    return AlertOut.of(alert, account.name)


# --- alert rules (slice 6.3) -------------------------------------------------------------------


class RuleIn(BaseModel):
    name: str
    active: bool = True
    kinds: list[str] = []
    signals: list[str] = []
    topics: list[str] = []
    action: str
    task_title: str | None = None


class RulePatch(BaseModel):
    name: str | None = None
    active: bool | None = None
    kinds: list[str] | None = None
    signals: list[str] | None = None
    topics: list[str] | None = None
    action: str | None = None
    task_title: str | None = None


class RuleOut(BaseModel):
    id: uuid.UUID
    name: str
    active: bool
    kinds: list[str]
    signals: list[str]
    topics: list[str]
    action: str
    task_title: str | None
    updated_at: datetime

    @classmethod
    def of(cls, rule: AlertRule) -> "RuleOut":
        return cls(
            id=rule.id,
            name=rule.name,
            active=rule.active,
            kinds=rule.kinds,
            signals=rule.signals,
            topics=rule.topics,
            action=rule.action,
            task_title=rule.task_title,
            updated_at=rule.updated_at,
        )


class Choice(BaseModel):
    key: str
    label: str


class RuleChoicesOut(BaseModel):
    actions: list[Choice]
    kinds: list[Choice]
    signals: list[Choice]
    topics: list[Choice]


KIND_LABELS = {
    "job_posting": "Job posting",
    "news": "News",
    "registry": "Companies House",
    "website": "Website change",
}


@router.get("/monitoring/rules")
async def list_rules(user: Member, db: DbSession) -> list[RuleOut]:
    return [RuleOut.of(r) for r in await rules.list_rules(db)]


@router.get("/monitoring/rule-choices")
async def rule_choices(user: Member) -> RuleChoicesOut:
    return RuleChoicesOut(
        actions=[Choice(key=k, label=rules.ACTION_LABELS[k]) for k in rules.ACTIONS],
        kinds=[Choice(key=k, label=KIND_LABELS[k]) for k in rules.KINDS],
        signals=[Choice(key=k, label=v) for k, v in SIGNAL_LABELS.items()],
        topics=[Choice(key=k, label=k.capitalize()) for k in rules.TOPICS],
    )


@router.post("/monitoring/rules", status_code=201)
async def create_rule(body: RuleIn, user: Admin, db: DbSession) -> RuleOut:
    return RuleOut.of(await rules.create(db, user=user, data=body.model_dump()))


@router.patch("/monitoring/rules/{rule_id}")
async def update_rule(rule_id: uuid.UUID, body: RulePatch, user: Admin, db: DbSession) -> RuleOut:
    data = body.model_dump(exclude_unset=True)
    return RuleOut.of(await rules.update(db, user=user, rule_id=rule_id, data=data))


@router.delete("/monitoring/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: uuid.UUID, user: Admin, db: DbSession) -> Response:
    await rules.delete(db, user=user, rule_id=rule_id)
    return Response(status_code=204)
