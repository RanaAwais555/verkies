"""Watchlists and signal monitoring (master context §15 Monitoring; slice 6.1).

A watched account is re-checked from the sources its latest research found: the job boards and
news feeds its own site links to, and its Companies House record (filings, officers). Every check
is stored as a monitoring check (a research run of kind "monitor", never reviewed, never listed
with research) holding what it read, so ranking, timing and the learning engine see new signals
like any others. A signal VROS had not seen before for that account becomes an alert and a line
on the timeline. Nothing is contacted and nothing is guessed: an account with no research has
nothing to check, and a source that fails is reported, never treated as "no news".
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.accounts import access
from app.accounts.models import Account
from app.audit import service as audit
from app.auth.models import User
from app.core.enums import AuditSource, JobStatus, ObservationArea, ReviewStatus, RunKind
from app.core.errors import NotFound
from app.crm import timeline
from app.evidence.models import Observation as ObservationRow
from app.intelligence.stage import persist_observation
from app.leads.ranking import SIGNAL_LABELS
from app.monitoring.models import MonitorAlert, Watch
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.registry import stage as registry
from app.research.crawler import PageSource
from app.research.models import ResearchRun
from app.scoring.stage import load_facts
from app.signals import jobs
from app.signals import stage as signals

KINDS = {"signal.job_posting": "job_posting", "signal.news": "news", "signal.filing": "registry"}


def _now() -> datetime:
    return datetime.now(UTC)


def fingerprint(key: str, value: dict[str, Any]) -> str:
    """The same posting, story or filing read again gives the same fingerprint."""
    ident = str(value.get("url") or value.get("title") or "").strip().lower()
    return f"{key}|{value.get('signal')}|{ident}|{value.get('published') or ''}"


# --- watching ----------------------------------------------------------------------------------


async def visible_account(db: AsyncSession, user: User, account_id: uuid.UUID) -> Account:
    account = await db.get(Account, account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")
    return account


async def watch(db: AsyncSession, *, user: User, account_id: uuid.UUID) -> None:
    account = await visible_account(db, user, account_id)
    existing = (
        await db.execute(
            select(Watch.id).where(Watch.account_id == account.id, Watch.user_id == user.id)
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(Watch(account_id=account.id, user_id=user.id))
        audit.record(
            db,
            action="account.watched",
            object_table="accounts",
            object_id=account.id,
            user_id=user.id,
            source=AuditSource.API,
        )
        await db.commit()


async def unwatch(db: AsyncSession, *, user: User, account_id: uuid.UUID) -> None:
    account = await visible_account(db, user, account_id)
    row = (
        await db.execute(
            select(Watch).where(Watch.account_id == account.id, Watch.user_id == user.id)
        )
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        audit.record(
            db,
            action="account.unwatched",
            object_table="accounts",
            object_id=account.id,
            user_id=user.id,
            source=AuditSource.API,
        )
        await db.commit()


@dataclass
class WatchView:
    account: Account
    watchers: int
    watching: bool
    last_checked_at: datetime | None
    open_alerts: int


async def watched(db: AsyncSession, *, user: User, mine: bool = True) -> list[WatchView]:
    stmt = (
        select(Account)
        .where(Account.deleted_at.is_(None))
        .join(Watch, Watch.account_id == Account.id)
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    if mine:
        stmt = stmt.where(Watch.user_id == user.id)
    accounts = list((await db.execute(stmt.distinct().order_by(Account.name))).scalars())
    ids = [a.id for a in accounts]
    if not ids:
        return []
    watchers = dict(
        (
            await db.execute(
                select(Watch.account_id, func.count())
                .where(Watch.account_id.in_(ids))
                .group_by(Watch.account_id)
            )
        ).all()
    )
    mine_ids = set(
        (
            await db.execute(
                select(Watch.account_id).where(Watch.account_id.in_(ids), Watch.user_id == user.id)
            )
        ).scalars()
    )
    checked = dict(
        (
            await db.execute(
                select(ResearchRun.account_id, func.max(ResearchRun.finished_at))
                .where(ResearchRun.account_id.in_(ids), ResearchRun.kind == RunKind.MONITOR)
                .group_by(ResearchRun.account_id)
            )
        ).all()
    )
    open_alerts = dict(
        (
            await db.execute(
                select(MonitorAlert.account_id, func.count())
                .where(MonitorAlert.account_id.in_(ids), MonitorAlert.reviewed_at.is_(None))
                .group_by(MonitorAlert.account_id)
            )
        ).all()
    )
    return [
        WatchView(
            account=a,
            watchers=watchers.get(a.id, 0),
            watching=a.id in mine_ids,
            last_checked_at=checked.get(a.id),
            open_alerts=open_alerts.get(a.id, 0),
        )
        for a in accounts
    ]


# --- checking ----------------------------------------------------------------------------------


@dataclass
class MonitorDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    source: PageSource
    fetcher: SafeHttpFetcher
    boards: jobs.JobBoards
    registries: registry.Registries


@dataclass
class CheckResult:
    account_id: uuid.UUID
    checked: bool
    reason: str | None = None
    run_id: uuid.UUID | None = None
    read: int = 0
    new: int = 0
    errors: list[str] = field(default_factory=list)


async def check_account(
    account_id: uuid.UUID,
    deps: MonitorDeps,
    *,
    requested_by: uuid.UUID | None = None,
    today: date | None = None,
) -> CheckResult:
    """Read the account's known sources again and alert on what is new."""
    today = today or _now().date()
    async with deps.sessionmaker() as db:
        account = await db.get(Account, account_id)
        if account is None or account.deleted_at is not None:
            return CheckResult(account_id, False, "account not found")
        latest = (
            await db.execute(
                select(ResearchRun)
                .where(
                    ResearchRun.account_id == account_id,
                    ResearchRun.kind == RunKind.RESEARCH,
                    ResearchRun.status == JobStatus.COMPLETED,
                )
                .order_by(ResearchRun.finished_at.desc().nulls_last())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            return CheckResult(account_id, False, "no completed research to know its sources")
        facts = await load_facts(db, latest)
        requester = (
            requested_by
            or (
                await db.execute(
                    select(Watch.user_id)
                    .where(Watch.account_id == account_id)
                    .order_by(Watch.created_at)
                    .limit(1)
                )
            ).scalar_one_or_none()
            or latest.requested_by_id
        )
        domain = latest.normalised_domain
        input_url = latest.input_url
        seen = {
            fingerprint(key, value or {})
            for key, value in (
                await db.execute(
                    select(ObservationRow.key, ObservationRow.value)
                    .join(ResearchRun, ResearchRun.id == ObservationRow.research_run_id)
                    .where(
                        ResearchRun.account_id == account_id,
                        ObservationRow.area == ObservationArea.SIGNALS,
                    )
                )
            ).all()
        }

    found, report = await signals.collect(facts, deps.source, deps.boards, today)
    registry_found, registry_report = await registry.collect(
        facts, domain, deps.fetcher, deps.registries, today
    )
    found += registry_found
    errors = list(report.get("errors", [])) + list(registry_report.get("errors", []))

    async with deps.sessionmaker() as db:
        now = _now()
        run = ResearchRun(
            input_url=input_url,
            normalised_domain=domain,
            account_id=account_id,
            requested_by_id=requester,
            kind=RunKind.MONITOR,
            status=JobStatus.COMPLETED,
            review_status=ReviewStatus.NOT_REQUIRED,
            started_at=now,
            finished_at=now,
            crawl_budget={},
            possible_duplicate_of=[],
            error="; ".join(errors) or None,
        )
        db.add(run)
        await db.flush()
        new: list[tuple[Any, ObservationRow]] = []
        for item in found:
            row = persist_observation(db, run.id, 0, item)
            if item.area is ObservationArea.SIGNALS:
                mark = fingerprint(item.key, item.value)
                if mark not in seen:
                    seen.add(mark)
                    new.append((item, row))
        await db.flush()
        for item, row in new:
            published = item.value.get("published")
            db.add(
                MonitorAlert(
                    account_id=account_id,
                    research_run_id=run.id,
                    observation_id=row.id,
                    kind=KINDS.get(item.key, item.key.removeprefix("signal.")),
                    signal=item.value.get("signal"),
                    title=str(item.value.get("title") or item.excerpt)[:500],
                    source_url=item.source_url,
                    happened_on=date.fromisoformat(published[:10]) if published else None,
                )
            )
        if new:
            labels = [
                SIGNAL_LABELS.get(str(i.value.get("signal")), str(i.value.get("title") or ""))
                for i, _ in new
            ]
            shown = ", ".join(dict.fromkeys(label for label in labels if label))[:300]
            timeline.add(
                db,
                account_id=account_id,
                event_type="monitoring.new_signals",
                summary=f"Monitoring found {len(new)} new signal{'s' if len(new) != 1 else ''}"
                + (f": {shown}." if shown else "."),
                actor_id=None,
                ref_table="research_runs",
                ref_id=run.id,
            )
        await db.commit()
        return CheckResult(
            account_id, True, None, run.id, read=len(found), new=len(new), errors=errors
        )


async def watched_account_ids(db: AsyncSession) -> list[uuid.UUID]:
    return list(
        (
            await db.execute(
                select(Watch.account_id)
                .join(Account, Account.id == Watch.account_id)
                .where(Account.deleted_at.is_(None))
                .distinct()
            )
        ).scalars()
    )


async def check_all(deps: MonitorDeps) -> list[CheckResult]:
    async with deps.sessionmaker() as db:
        ids = await watched_account_ids(db)
    return [await check_account(account_id, deps) for account_id in ids]


# --- alerts ------------------------------------------------------------------------------------


async def alerts(
    db: AsyncSession,
    *,
    user: User,
    account_id: uuid.UUID | None = None,
    open_only: bool = False,
    mine: bool = False,
    limit: int = 200,
) -> list[tuple[MonitorAlert, Account]]:
    stmt = (
        select(MonitorAlert, Account)
        .join(Account, Account.id == MonitorAlert.account_id)
        .where(Account.deleted_at.is_(None))
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    if account_id is not None:
        stmt = stmt.where(MonitorAlert.account_id == account_id)
    if open_only:
        stmt = stmt.where(MonitorAlert.reviewed_at.is_(None))
    if mine:
        stmt = stmt.where(
            MonitorAlert.account_id.in_(select(Watch.account_id).where(Watch.user_id == user.id))
        )
    stmt = stmt.order_by(MonitorAlert.created_at.desc(), MonitorAlert.id).limit(limit)
    return [(a, acc) for a, acc in (await db.execute(stmt)).all()]


async def review_alert(db: AsyncSession, *, user: User, alert_id: uuid.UUID) -> MonitorAlert:
    alert = await db.get(MonitorAlert, alert_id)
    if alert is None:
        raise NotFound("Alert not found.")
    await visible_account(db, user, alert.account_id)
    if alert.reviewed_at is None:
        alert.reviewed_at = _now()
        alert.reviewed_by_id = user.id
        await db.commit()
    return alert
