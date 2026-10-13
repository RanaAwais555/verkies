"""Watchlists and monitoring (master context §15 Monitoring; slices 6.1 to 6.3).

A watched account is re-checked from the sources its latest research found: the job boards and
news feeds its own site links to, and its Companies House record (filings, officers). Every check
is stored as a monitoring check (a research run of kind "monitor", never reviewed, never listed
with research) holding what it read, so ranking, timing and the learning engine see new signals
like any others. A signal VROS had not seen before for that account becomes an alert and a line
on the timeline. Nothing is contacted and nothing is guessed: an account with no research has
nothing to check, and a source that fails is reported, never treated as "no news".

The same check reads the account's own pages again and records what changed on its website
(app.monitoring.website): each change is an alert of kind "website" with the text before and after.
The alert rules (app.monitoring.rules) then flag the new alerts, create follow-up tasks and tell
the account's watchers in the app.
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
from app.config import get_settings
from app.core.enums import (
    AuditSource,
    EvidenceType,
    JobStatus,
    ObservationArea,
    ReviewStatus,
    RunKind,
)
from app.core.errors import NotFound
from app.crm import timeline
from app.evidence.models import Observation as ObservationRow
from app.intelligence.stage import persist_observation
from app.intelligence.types import Observation
from app.leads.ranking import SIGNAL_LABELS
from app.monitoring import rules, website
from app.monitoring.models import MonitorAlert, Watch
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.storage import Storage
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
    attention: str | None = None


async def watched(
    db: AsyncSession, *, user: User, mine: bool = True, limit: int = 500
) -> list[WatchView]:
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
    accounts = list(
        (await db.execute(stmt.distinct().order_by(Account.name).limit(limit))).scalars()
    )
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
    flags = await attention(db, ids)
    return [
        WatchView(
            account=a,
            attention=flags.get(a.id),
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
    storage: Storage


@dataclass
class CheckResult:
    account_id: uuid.UUID
    checked: bool
    reason: str | None = None
    run_id: uuid.UUID | None = None
    read: int = 0
    new: int = 0
    changes: int = 0
    flagged: int = 0
    tasks: int = 0
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
        pages = await website.snapshots(db, latest.id, deps.storage)
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
    read = await website.reread(deps.source, pages)
    changes = website.compare(read)
    errors = list(report.get("errors", [])) + list(registry_report.get("errors", [])) + read.errors

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
        changed: list[tuple[website.Change, ObservationRow]] = []
        for change in changes:
            observation = Observation(
                ObservationArea.WEBSITE,
                "website.change",
                {"title": change.title, **change.detail()},
                change.url,
                change.after[:300],
                evidence_type=EvidenceType.PAGE_CONTENT,
            )
            changed.append((change, persist_observation(db, run.id, 0, observation)))
        await db.flush()
        created: list[MonitorAlert] = []
        for change, row in changed:
            created.append(
                MonitorAlert(
                    account_id=account_id,
                    research_run_id=run.id,
                    observation_id=row.id,
                    kind="website",
                    title=change.title[:500],
                    source_url=change.url,
                    detail=change.detail(),
                )
            )
        if changed:
            titles = "; ".join(c.title for c, _ in changed[:5])[:300]
            plural = "s" if len(changed) != 1 else ""
            more = "; …" if len(changed) > 5 else "."
            timeline.add(
                db,
                account_id=account_id,
                event_type="monitoring.website_changes",
                summary=f"Monitoring found {len(changed)} website change{plural}: {titles}{more}",
                actor_id=None,
                ref_table="research_runs",
                ref_id=run.id,
            )
        for item, row in new:
            published = item.value.get("published")
            created.append(
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
        db.add_all(created)
        await db.flush()
        account = await db.get(Account, account_id)
        assert account is not None
        applied = await rules.apply(db, account, created, run_id=run.id, settings=get_settings())
        await db.commit()
        return CheckResult(
            account_id,
            True,
            None,
            run.id,
            read=len(found) + len(read.pages),
            new=len(new),
            changes=len(changed),
            flagged=applied.flagged,
            tasks=len(applied.tasks or []),
            errors=errors,
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
    raised: bool = False,
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
    if raised:
        stmt = stmt.where(MonitorAlert.raised.is_not(None))
    if mine:
        stmt = stmt.where(
            MonitorAlert.account_id.in_(select(Watch.account_id).where(Watch.user_id == user.id))
        )
    stmt = stmt.order_by(MonitorAlert.created_at.desc(), MonitorAlert.id).limit(limit)
    return [(a, acc) for a, acc in (await db.execute(stmt)).all()]


async def attention(db: AsyncSession, account_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Each account's flag: the strongest raised by its unreviewed alerts."""
    if not account_ids:
        return {}
    found: dict[uuid.UUID, set[str]] = {}
    for account_id, raised in (
        await db.execute(
            select(MonitorAlert.account_id, MonitorAlert.raised)
            .where(
                MonitorAlert.account_id.in_(account_ids),
                MonitorAlert.reviewed_at.is_(None),
                MonitorAlert.raised.is_not(None),
            )
            .distinct()
        )
    ).all():
        found.setdefault(account_id, set()).add(str(raised))
    return {a: flag for a, flags in found.items() if (flag := rules.strongest(flags))}


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
