"""Client health and the retention engine (master context §14; slice 4.2).

Every client (an account of type customer) is Green, Yellow or Red, computed from the records on
every read, with each reason it gives:

Red when any of:
- an open project is marked At Risk;
- an open project has a high risk open;
- a milestone is `client_milestone_red_days` or more overdue;
- nobody has been in contact for `client_quiet_red_days`;
- the latest feedback (within `client_feedback_days`) is negative.

Yellow when any of:
- an open project is On Hold, or past its target date;
- a milestone is overdue, or a task on the account is;
- an open project has a medium risk open;
- nobody has been in contact for `client_quiet_yellow_days`;
- `client_unanswered_messages` messages have gone to them without a reply.

Green otherwise. Contact means a logged call, meeting, email or message (notes are internal); the
clock starts at the client-since date. Nothing is estimated: satisfaction is only what a person
recorded the client saying.

The retention engine is a daily sweep (and a "check now"): it keeps the history of each client's
colour, and when a client turns Red it raises "Client risk detected" on the timeline and gives the
account manager a follow-up task. It never contacts the client.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account
from app.audit import service as audit
from app.auth.models import User
from app.clients.models import (
    ClientFeedback,
    ClientHealthSnapshot,
    Milestone,
    Project,
    ProjectRisk,
)
from app.clients.service import CLOSED
from app.config import Settings, get_settings
from app.core.enums import (
    AccountType,
    AuditSource,
    HealthColour,
    ProjectStatus,
    RiskSeverity,
    Sentiment,
    TaskStatus,
)
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.crm import timeline
from app.crm.activities import Relationship, relationship
from app.crm.models import Activity, Task
from app.prospects.service import add_business_days

OPEN_TASK = (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)
RISK_TASK_PREFIX = "Client risk detected"
ORDER = {HealthColour.GREEN: 0, HealthColour.YELLOW: 1, HealthColour.RED: 2}


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Reason:
    level: Literal["red", "yellow"]
    text: str

    def as_dict(self) -> dict[str, str]:
        return {"level": self.level, "text": self.text}


@dataclass
class ProjectFacts:
    name: str
    status: ProjectStatus
    target_date: date | None
    late_milestones: list[tuple[str, date]] = field(default_factory=list)
    open_risks: list[tuple[RiskSeverity, str]] = field(default_factory=list)


@dataclass
class Facts:
    client_since: date | None
    projects: list[ProjectFacts]  # open projects only
    overdue_tasks: int
    relationship: Relationship
    feedback: ClientFeedback | None  # the latest


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def assess(facts: Facts, now: datetime, settings: Settings) -> tuple[HealthColour, list[Reason]]:
    """The colour and every reason for it. Red reasons come first."""
    today = now.date()
    red: list[Reason] = []
    yellow: list[Reason] = []

    for p in facts.projects:
        if p.status is ProjectStatus.AT_RISK:
            red.append(Reason("red", f"{p.name} is marked at risk"))
        elif p.status is ProjectStatus.ON_HOLD:
            yellow.append(Reason("yellow", f"{p.name} is on hold"))
        if p.target_date is not None and p.target_date < today:
            yellow.append(Reason("yellow", f"{p.name} is past its target date"))
        for severity, description in p.open_risks:
            if severity is RiskSeverity.HIGH:
                red.append(Reason("red", f"{p.name}: high risk open: {description[:120]}"))
            elif severity is RiskSeverity.MEDIUM:
                yellow.append(Reason("yellow", f"{p.name}: medium risk open: {description[:120]}"))
        for name, due in p.late_milestones:
            days = (today - due).days
            text = f"{p.name}: milestone {name} is {_plural(days, 'day')} overdue"
            if days >= settings.client_milestone_red_days:
                red.append(Reason("red", text))
            else:
                yellow.append(Reason("yellow", text))

    if facts.overdue_tasks:
        yellow.append(Reason("yellow", f"{_plural(facts.overdue_tasks, 'overdue task')}"))

    rel = facts.relationship
    since = rel.latest_interaction_at
    if since is None and facts.client_since is not None:
        since = datetime.combine(facts.client_since, time.min, tzinfo=UTC)
    if since is not None:
        quiet = (now - since).days
        what = "No contact" if rel.latest_interaction_at else "No contact since becoming a client"
        if quiet >= settings.client_quiet_red_days:
            red.append(Reason("red", f"{what} for {quiet} days"))
        elif quiet >= settings.client_quiet_yellow_days:
            yellow.append(Reason("yellow", f"{what} for {quiet} days"))
    if rel.attempts_since_reply >= settings.client_unanswered_messages:
        unanswered = _plural(rel.attempts_since_reply, "message")
        yellow.append(Reason("yellow", f"{unanswered} without a reply"))

    fb = facts.feedback
    recent = fb is not None and (today - fb.received_on).days <= settings.client_feedback_days
    if fb is not None and recent and fb.sentiment is Sentiment.NEGATIVE:
        note = f": {fb.note[:120]}" if fb.note else ""
        red.append(Reason("red", f"Negative feedback on {fb.received_on.isoformat()}{note}"))

    if red:
        return HealthColour.RED, red + yellow
    if yellow:
        return HealthColour.YELLOW, yellow
    return HealthColour.GREEN, []


# --- gathering the facts -----------------------------------------------------------------------


async def gather(
    db: AsyncSession, accounts: list[Account], now: datetime
) -> dict[uuid.UUID, Facts]:
    ids = [a.id for a in accounts]
    if not ids:
        return {}
    today = now.date()
    projects: dict[uuid.UUID, list[ProjectFacts]] = defaultdict(list)
    by_project: dict[uuid.UUID, ProjectFacts] = {}
    for p in (
        await db.execute(
            select(Project)
            .where(
                Project.account_id.in_(ids),
                Project.deleted_at.is_(None),
                Project.status.not_in(CLOSED),
            )
            .order_by(Project.created_at)
        )
    ).scalars():
        facts = ProjectFacts(name=p.name, status=p.status, target_date=p.target_date)
        projects[p.account_id].append(facts)
        by_project[p.id] = facts
    if by_project:
        for m in (
            await db.execute(
                select(Milestone)
                .where(
                    Milestone.project_id.in_(list(by_project)),
                    Milestone.completed_at.is_(None),
                    Milestone.due_date < today,
                )
                .order_by(Milestone.due_date)
            )
        ).scalars():
            assert m.due_date is not None
            by_project[m.project_id].late_milestones.append((m.name, m.due_date))
        for r in (
            await db.execute(
                select(ProjectRisk)
                .where(
                    ProjectRisk.project_id.in_(list(by_project)), ProjectRisk.resolved_at.is_(None)
                )
                .order_by(ProjectRisk.created_at)
            )
        ).scalars():
            by_project[r.project_id].open_risks.append((r.severity, r.description))

    overdue = dict(
        (
            await db.execute(
                select(Task.account_id, func.count())
                .where(
                    Task.account_id.in_(ids),
                    Task.deleted_at.is_(None),
                    Task.status.in_(OPEN_TASK),
                    Task.due_at < now,
                )
                .group_by(Task.account_id)
            )
        ).all()
    )
    touches: dict[uuid.UUID, list[Any]] = defaultdict(list)
    for account_id, occurred_at, direction in (
        await db.execute(
            select(Activity.account_id, Activity.occurred_at, Activity.direction).where(
                Activity.account_id.in_(ids)
            )
        )
    ).all():
        touches[account_id].append((occurred_at, direction))
    latest_feedback: dict[uuid.UUID, ClientFeedback] = {}
    for fb in (
        await db.execute(
            select(ClientFeedback)
            .where(ClientFeedback.account_id.in_(ids))
            .order_by(ClientFeedback.received_on.desc(), ClientFeedback.created_at.desc())
        )
    ).scalars():
        latest_feedback.setdefault(fb.account_id, fb)
    return {
        a.id: Facts(
            client_since=a.client_since,
            projects=projects[a.id],
            overdue_tasks=overdue.get(a.id, 0),
            relationship=relationship(touches[a.id]),
            feedback=latest_feedback.get(a.id),
        )
        for a in accounts
    }


@dataclass
class ClientView:
    account: Account
    colour: HealthColour
    reasons: list[Reason]
    facts: Facts
    manager_name: str | None = None


async def _views(db: AsyncSession, accounts: list[Account], now: datetime) -> list[ClientView]:
    settings = get_settings()
    facts = await gather(db, accounts, now)
    manager_ids = {a.account_manager_id for a in accounts if a.account_manager_id}
    names = (
        dict((await db.execute(select(User.id, User.name).where(User.id.in_(manager_ids)))).all())
        if manager_ids
        else {}
    )
    views = []
    for account in accounts:
        colour, reasons = assess(facts[account.id], now, settings)
        views.append(
            ClientView(
                account=account,
                colour=colour,
                reasons=reasons,
                facts=facts[account.id],
                manager_name=names.get(account.account_manager_id)
                if account.account_manager_id
                else None,
            )
        )
    return views


async def list_clients(
    db: AsyncSession,
    *,
    user: User,
    colour: HealthColour | None = None,
    mine: bool = False,
    now: datetime | None = None,
) -> list[ClientView]:
    """Every current client, worst health first."""
    stmt = select(Account).where(
        Account.account_type == AccountType.CUSTOMER, Account.deleted_at.is_(None)
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    if mine:
        stmt = stmt.where(func.coalesce(Account.account_manager_id, Account.owner_id) == user.id)
    accounts = list((await db.execute(stmt.order_by(Account.name))).scalars())
    views = await _views(db, accounts, now or _now())
    if colour is not None:
        views = [v for v in views if v.colour is colour]
    return sorted(views, key=lambda v: (-ORDER[v.colour], -len(v.reasons), v.account.name))


async def _client(db: AsyncSession, user: User, account_id: uuid.UUID) -> Account:
    account = await db.get(Account, account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")
    return account


@dataclass
class AccountHealth:
    current: ClientView | None  # None when the account is not a client
    history: list[ClientHealthSnapshot]
    feedback: list[ClientFeedback]
    recorded_by: dict[uuid.UUID, str]


async def account_health(db: AsyncSession, *, user: User, account_id: uuid.UUID) -> AccountHealth:
    account = await _client(db, user, account_id)
    current = None
    if account.account_type is AccountType.CUSTOMER:
        current = (await _views(db, [account], _now()))[0]
    history = list(
        (
            await db.execute(
                select(ClientHealthSnapshot)
                .where(ClientHealthSnapshot.account_id == account.id)
                .order_by(ClientHealthSnapshot.assessed_at.desc())
                .limit(20)
            )
        ).scalars()
    )
    feedback = list(
        (
            await db.execute(
                select(ClientFeedback)
                .where(ClientFeedback.account_id == account.id)
                .order_by(ClientFeedback.received_on.desc(), ClientFeedback.created_at.desc())
                .limit(50)
            )
        ).scalars()
    )
    ids = {f.recorded_by_id for f in feedback if f.recorded_by_id}
    names = (
        dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).all())
        if ids
        else {}
    )
    return AccountHealth(current=current, history=history, feedback=feedback, recorded_by=names)


# --- the retention engine ----------------------------------------------------------------------


@dataclass
class SweepResult:
    assessed: int = 0
    changed: int = 0
    risks_raised: int = 0


def _risk_description(reasons: list[Reason]) -> str:
    lines = [f"- {r.text}" for r in reasons]
    return "Client health turned Red because:\n" + "\n".join(lines)


async def _raise_risk(
    db: AsyncSession, account: Account, reasons: list[Reason], now: datetime, settings: Settings
) -> bool:
    """A follow-up task for whoever looks after the client, unless one is already open."""
    open_already = (
        await db.execute(
            select(Task.id).where(
                Task.account_id == account.id,
                Task.deleted_at.is_(None),
                Task.status.in_(OPEN_TASK),
                Task.title.startswith(RISK_TASK_PREFIX),
            )
        )
    ).first()
    timeline.add(
        db,
        account_id=account.id,
        event_type="client.risk_detected",
        summary=f"Client risk detected: {reasons[0].text}"
        + (f" (and {_plural(len(reasons) - 1, 'more reason')})" if len(reasons) > 1 else "")
        + ".",
        actor_id=None,
    )
    if open_already is not None:
        return False
    task = Task(
        account_id=account.id,
        title=f"{RISK_TASK_PREFIX}: talk to {account.name}"[:200],
        description=_risk_description(reasons),
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
            "reason": "client_risk_detected",
        },
    )
    return True


async def sweep(
    db: AsyncSession,
    *,
    account_ids: list[uuid.UUID] | None = None,
    now: datetime | None = None,
) -> SweepResult:
    """Assess clients, record each colour change, and raise a risk when a client turns Red."""
    now = now or _now()
    settings = get_settings()
    stmt = select(Account).where(
        Account.account_type == AccountType.CUSTOMER, Account.deleted_at.is_(None)
    )
    if account_ids is not None:
        stmt = stmt.where(Account.id.in_(account_ids))
    accounts = list((await db.execute(stmt.with_for_update())).scalars())
    result = SweepResult(assessed=len(accounts))
    if not accounts:
        return result
    latest: dict[uuid.UUID, HealthColour] = {}
    for account_id, colour in (
        await db.execute(
            select(ClientHealthSnapshot.account_id, ClientHealthSnapshot.colour)
            .where(ClientHealthSnapshot.account_id.in_([a.id for a in accounts]))
            .order_by(ClientHealthSnapshot.assessed_at.desc())
        )
    ).all():
        latest.setdefault(account_id, colour)
    for view in await _views(db, accounts, now):
        before = latest.get(view.account.id)
        if before is view.colour:
            continue
        result.changed += 1
        db.add(
            ClientHealthSnapshot(
                account_id=view.account.id,
                colour=view.colour,
                reasons=[r.as_dict() for r in view.reasons],
                assessed_at=now,
            )
        )
        timeline.add(
            db,
            account_id=view.account.id,
            event_type="client.health_changed",
            summary=f"Client health: {before.value.capitalize() + ' to ' if before else ''}"
            f"{view.colour.value.capitalize()}"
            + (f" ({view.reasons[0].text})" if view.reasons else "")
            + ".",
            actor_id=None,
        )
        if view.colour is HealthColour.RED and await _raise_risk(
            db, view.account, view.reasons, now, settings
        ):
            result.risks_raised += 1
    await db.commit()
    return result


# --- feedback and ending the relationship ------------------------------------------------------


async def record_feedback(
    db: AsyncSession,
    *,
    user: User,
    account_id: uuid.UUID,
    sentiment: Sentiment,
    note: str | None,
    received_on: date | None,
    project_id: uuid.UUID | None,
) -> ClientFeedback:
    account = await _client(db, user, account_id)
    if account.account_type is not AccountType.CUSTOMER:
        raise ValidationFailed("Feedback is recorded for clients.", code="not_a_client")
    when = received_on or _now().date()
    if when > _now().date():
        raise ValidationFailed("Feedback cannot be from the future.")
    if project_id is not None:
        project = await db.get(Project, project_id)
        if project is None or project.account_id != account.id or project.deleted_at:
            raise ValidationFailed("That project is not on this account.")
    feedback = ClientFeedback(
        account_id=account.id,
        project_id=project_id,
        sentiment=sentiment,
        note=(note or "").strip() or None,
        received_on=when,
        recorded_by_id=user.id,
    )
    db.add(feedback)
    await db.flush()
    timeline.add(
        db,
        account_id=account.id,
        event_type="client.feedback",
        summary=f"{sentiment.value.capitalize()} feedback from the client"
        + (f": {feedback.note[:200]}" if feedback.note else "")
        + ".",
        actor_id=user.id,
        ref_table="client_feedback",
        ref_id=feedback.id,
    )
    audit.record(
        db,
        action="client_feedback.recorded",
        object_table="client_feedback",
        object_id=feedback.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"account_id": str(account.id), "sentiment": sentiment.value},
    )
    await db.commit()
    # Negative feedback should not wait for tomorrow's sweep.
    await sweep(db, account_ids=[account.id])
    return feedback


async def end_client(
    db: AsyncSession, *, user: User, account_id: uuid.UUID, reason: str
) -> Account:
    """The client relationship ended: the account becomes a former client, keeping everything."""
    account = await _client(db, user, account_id)
    if account.account_type is not AccountType.CUSTOMER:
        raise ValidationFailed("This account is not a current client.", code="not_a_client")
    open_projects = (
        (
            await db.execute(
                select(Project.name).where(
                    Project.account_id == account.id,
                    Project.deleted_at.is_(None),
                    Project.status.not_in(CLOSED),
                )
            )
        )
        .scalars()
        .all()
    )
    if open_projects:
        raise Conflict(
            "Complete or cancel the open projects first: " + ", ".join(open_projects) + ".",
            code="open_projects",
        )
    account.account_type = AccountType.FORMER_CUSTOMER
    timeline.add(
        db,
        account_id=account.id,
        event_type="account.client_ended",
        summary=f"No longer a client: {reason.strip()}",
        actor_id=user.id,
    )
    audit.record(
        db,
        action="account.client_ended",
        object_table="accounts",
        object_id=account.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value={"account_type": AccountType.CUSTOMER.value},
        new_value={"account_type": AccountType.FORMER_CUSTOMER.value},
        reason=reason.strip(),
    )
    await db.commit()
    return account
