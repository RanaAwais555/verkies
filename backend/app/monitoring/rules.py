"""Alert rules (master context §15 Monitoring: "a new signal may raise Opportunity Detected or
Account Requires Review, or create a task"; slice 6.3).

When a monitoring check records alerts, each active rule that matches an alert acts on it:
- opportunity_detected or requires_review: the alert carries that flag (Opportunity Detected
  outranks Requires review). An account is flagged while it has an unreviewed flagged alert, so
  reviewing the alerts clears it; nothing is stored that could go stale.
- task: one follow-up task per rule and check for the account's manager or owner, listing the
  alerts, unless that rule's task is still open for the account.

Watchers are told in the app; the task's owner is told about the task. Nothing contacts anyone.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import Account
from app.audit import service as audit
from app.auth.models import User
from app.config import Settings
from app.core.enums import AuditSource, TaskStatus
from app.core.errors import NotFound, ValidationFailed
from app.crm import timeline
from app.crm.models import Task
from app.leads.ranking import SIGNAL_LABELS
from app.monitoring.models import AlertRule, MonitorAlert, Watch
from app.notifications import service as notifications
from app.prospects.service import add_business_days

FLAGS = ("opportunity_detected", "requires_review")  # strongest first
ACTIONS = (*FLAGS, "task")
ACTION_LABELS = {
    "opportunity_detected": "Opportunity Detected",
    "requires_review": "Account Requires Review",
    "task": "Follow-up task",
}
KINDS = ("job_posting", "news", "registry", "website")
TOPICS = ("services", "pricing", "technology", "contact", "pages")
OPEN_TASK = (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)


def matches(rule: AlertRule, alert: MonitorAlert) -> bool:
    topic = (alert.detail or {}).get("topic")
    return (
        (not rule.kinds or alert.kind in rule.kinds)
        and (not rule.signals or alert.signal in rule.signals)
        and (not rule.topics or topic in rule.topics)
    )


def task_title(rule: AlertRule, account: Account) -> str:
    return (rule.task_title or f"Follow up: {rule.name}").replace("{account}", account.name)[:200]


def strongest(flags: set[str]) -> str | None:
    return next((f for f in FLAGS if f in flags), None)


@dataclass
class Applied:
    flagged: int = 0
    tasks: list[Task] | None = None


async def apply(
    db: AsyncSession,
    account: Account,
    alerts: list[MonitorAlert],
    *,
    run_id: uuid.UUID,
    settings: Settings,
    now: datetime | None = None,
) -> Applied:
    """Run the active rules over a check's new alerts (already flushed, so they have ids)."""
    now = now or datetime.now(UTC)
    result = Applied(tasks=[])
    if not alerts:
        return result
    rules = list(
        (
            await db.execute(
                select(AlertRule)
                .where(AlertRule.active.is_(True))
                .order_by(AlertRule.created_at, AlertRule.name, AlertRule.id)
            )
        ).scalars()
    )
    wants_task: dict[uuid.UUID, list[MonitorAlert]] = defaultdict(list)
    for alert in alerts:
        hit = [rule for rule in rules if matches(rule, alert)]
        alert.rules = [{"id": str(r.id), "name": r.name, "action": r.action} for r in hit]
        alert.raised = strongest({r.action for r in hit})
        result.flagged += alert.raised is not None
        for rule in hit:
            if rule.action == "task":
                wants_task[rule.id].append(alert)
    by_id = {r.id: r for r in rules}
    for rule_id, matched in wants_task.items():
        task_id, created = await _task(
            db, account, by_id[rule_id], matched, settings=settings, now=now
        )
        if created is not None:
            result.tasks.append(created)  # type: ignore[union-attr]
        for alert in matched:
            alert.task_id = alert.task_id or task_id
    if result.flagged:
        raised = strongest({a.raised for a in alerts if a.raised})
        timeline.add(
            db,
            account_id=account.id,
            event_type=f"monitoring.{raised}",
            summary=f"{ACTION_LABELS[raised or '']}: "
            + "; ".join(a.title for a in alerts if a.raised)[:280]
            + ".",
            actor_id=None,
            ref_table="research_runs",
            ref_id=run_id,
        )
    await _notify(db, account, alerts, result.tasks or [])
    return result


async def _task(
    db: AsyncSession,
    account: Account,
    rule: AlertRule,
    alerts: list[MonitorAlert],
    *,
    settings: Settings,
    now: datetime,
) -> tuple[uuid.UUID, Task | None]:
    """(the task the alerts belong to, the task if this created it). While the rule's task is
    still open for the account, new alerts join it instead of adding another."""
    title = task_title(rule, account)
    open_already = (
        await db.execute(
            select(Task.id)
            .where(
                Task.account_id == account.id,
                Task.deleted_at.is_(None),
                Task.status.in_(OPEN_TASK),
                Task.title == title,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if open_already is not None:
        return open_already, None
    lines = [f'Alert rule "{rule.name}" matched what monitoring found:']
    lines += [f"- {a.title} ({a.source_url})" for a in alerts]
    task = Task(
        account_id=account.id,
        title=title,
        description="\n".join(lines),
        owner_id=account.account_manager_id or account.owner_id,
        due_at=add_business_days(now, settings.task_due_business_days),
    )
    db.add(task)
    await db.flush()
    if account.next_activity_at is None or (task.due_at and task.due_at < account.next_activity_at):
        account.next_activity_at = task.due_at
    audit.record(
        db,
        action="task.created",
        object_table="tasks",
        object_id=task.id,
        user_id=None,
        source=AuditSource.SYSTEM,
        new_value={
            "title": task.title,
            "owner_id": str(task.owner_id) if task.owner_id else None,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "reason": "alert_rule",
            "rule_id": str(rule.id),
        },
    )
    return task.id, task


async def _notify(
    db: AsyncSession, account: Account, alerts: list[MonitorAlert], tasks: list[Task]
) -> None:
    watchers = set(
        (await db.execute(select(Watch.user_id).where(Watch.account_id == account.id))).scalars()
    )
    raised = strongest({a.raised for a in alerts if a.raised})
    count = f"{len(alerts)} new alert{'s' if len(alerts) != 1 else ''}"
    await notifications.notify(
        db,
        watchers,
        kind="monitoring_alert",
        title=f"{account.name}: {ACTION_LABELS[raised]}" if raised else f"{account.name}: {count}",
        body="; ".join(a.title for a in alerts[:5])[:500] + ("; …" if len(alerts) > 5 else ""),
        account_id=account.id,
        link=f"/accounts/{account.id}",
    )
    for task in tasks:
        if task.owner_id is not None:
            await notifications.notify(
                db,
                {task.owner_id},
                kind="rule_task",
                title=f"New task: {task.title}",
                body=f"Due {task.due_at:%d %b %Y}." if task.due_at else None,
                account_id=account.id,
                link=f"/accounts/{account.id}",
            )


# --- managing rules ----------------------------------------------------------------------------


def _clean(values: list[str], allowed: tuple[str, ...] | set[str], what: str) -> list[str]:
    unknown = sorted(set(values) - set(allowed))
    if unknown:
        raise ValidationFailed(f"Unknown {what}: {', '.join(unknown)}.")
    return sorted(set(values))


def validate(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    if "name" in out:
        out["name"] = (out["name"] or "").strip()
        if not out["name"]:
            raise ValidationFailed("Give the rule a name.")
    if "action" in out and out["action"] not in ACTIONS:
        raise ValidationFailed("Choose what the rule does.")
    if "kinds" in out:
        out["kinds"] = _clean(out["kinds"], KINDS, "alert kind")
    if "signals" in out:
        out["signals"] = _clean(out["signals"], set(SIGNAL_LABELS), "signal")
    if "topics" in out:
        out["topics"] = _clean(out["topics"], TOPICS, "website topic")
    if "task_title" in out:
        out["task_title"] = (out["task_title"] or "").strip() or None
    return out


def _check_complete(rule: AlertRule) -> None:
    if not (rule.kinds or rule.signals or rule.topics):
        raise ValidationFailed("Say which alerts the rule is for: a kind, a signal or a topic.")


async def list_rules(db: AsyncSession) -> list[AlertRule]:
    return list(
        (
            await db.execute(
                select(AlertRule).order_by(AlertRule.created_at, AlertRule.name, AlertRule.id)
            )
        ).scalars()
    )


def _snapshot(rule: AlertRule) -> dict[str, Any]:
    return {
        "name": rule.name,
        "active": rule.active,
        "kinds": rule.kinds,
        "signals": rule.signals,
        "topics": rule.topics,
        "action": rule.action,
        "task_title": rule.task_title,
    }


async def create(db: AsyncSession, *, user: User, data: dict[str, Any]) -> AlertRule:
    data = validate(data)
    rule = AlertRule(
        name=data["name"],
        active=data.get("active", True),
        kinds=data.get("kinds", []),
        signals=data.get("signals", []),
        topics=data.get("topics", []),
        action=data["action"],
        task_title=data.get("task_title"),
        created_by_id=user.id,
    )
    _check_complete(rule)
    db.add(rule)
    await db.flush()
    audit.record(
        db,
        action="alert_rule.created",
        object_table="alert_rules",
        object_id=rule.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value=_snapshot(rule),
    )
    await db.commit()
    await db.refresh(rule)
    return rule


async def update(
    db: AsyncSession, *, user: User, rule_id: uuid.UUID, data: dict[str, Any]
) -> AlertRule:
    rule = await db.get(AlertRule, rule_id)
    if rule is None:
        raise NotFound("Rule not found.")
    before = _snapshot(rule)
    for key, value in validate(data).items():
        setattr(rule, key, value)
    _check_complete(rule)
    audit.record(
        db,
        action="alert_rule.updated",
        object_table="alert_rules",
        object_id=rule.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value=before,
        new_value=_snapshot(rule),
    )
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete(db: AsyncSession, *, user: User, rule_id: uuid.UUID) -> None:
    rule = await db.get(AlertRule, rule_id)
    if rule is None:
        raise NotFound("Rule not found.")
    audit.record(
        db,
        action="alert_rule.deleted",
        object_table="alert_rules",
        object_id=rule.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value=_snapshot(rule),
    )
    await db.delete(rule)
    await db.commit()
