"""Client conversion and lightweight projects (master context §14; slice 4.1).

Converting a won deal keeps the same Account and everything on it (contacts, deal, opportunity,
service, value, history, evidence): the account becomes a customer, gets an account manager, and
may get a project with milestones and a kick-off task. Nothing here judges how a project is going;
the facts shown (overdue milestones, open risks, overdue tasks) are read from what people entered.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any, cast

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account
from app.audit import service as audit
from app.auth.models import User
from app.catalogue.models import Service
from app.clients.models import Milestone, Project, ProjectRisk
from app.core.enums import (
    AccountType,
    AuditSource,
    ProjectStatus,
    RiskSeverity,
    StageOutcome,
    TaskStatus,
)
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.crm import service as crm
from app.crm import timeline
from app.crm.models import Opportunity, Task
from app.deals.models import Deal

CLOSED = (ProjectStatus.COMPLETED, ProjectStatus.CANCELLED)
OPEN_TASK = (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)
# Accounts that cannot become clients: they are not companies Verkies works for.
NOT_CONVERTIBLE = (AccountType.COMPETITOR, AccountType.SUPPRESSED)
STATUS_LABELS = {
    ProjectStatus.NOT_STARTED: "Not started",
    ProjectStatus.PLANNING: "Planning",
    ProjectStatus.ACTIVE: "Active",
    ProjectStatus.AT_RISK: "At risk",
    ProjectStatus.ON_HOLD: "On hold",
    ProjectStatus.COMPLETED: "Completed",
    ProjectStatus.CANCELLED: "Cancelled",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _today() -> date:
    return _now().date()


def _plain(value: Any) -> Any:
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value.value if hasattr(value, "value") else value


async def _active_user(db: AsyncSession, user_id: uuid.UUID | None, what: str) -> User | None:
    if user_id is None:
        return None
    found = await db.get(User, user_id)
    if found is None or not found.is_active:
        raise ValidationFailed(f"The {what} must be an active team member.", code="invalid_user")
    return found


async def _service(db: AsyncSession, service_id: uuid.UUID | None) -> Service | None:
    if service_id is None:
        return None
    found = await db.get(Service, service_id)
    if found is None:
        raise ValidationFailed("That service is not in the catalogue.", code="invalid_service")
    return found


def _check_dates(start: date | None, target: date | None) -> None:
    if start is not None and target is not None and target < start:
        raise ValidationFailed("The target date is before the start date.", code="invalid_dates")


# --- reading projects --------------------------------------------------------------------------


@dataclass
class ProjectView:
    project: Project
    account: Account
    service_name: str | None = None
    owner_name: str | None = None
    deal: Deal | None = None
    milestones: list[Milestone] = field(default_factory=list)
    risks: list[ProjectRisk] = field(default_factory=list)
    open_tasks: int = 0
    overdue_tasks: int = 0
    attention: list[str] = field(default_factory=list)


def attention_reasons(
    project: Project,
    milestones: list[Milestone],
    risks: list[ProjectRisk],
    overdue_tasks: int,
    today: date,
) -> list[str]:
    """Plain facts about an open project that someone should look at. None are guesses: each is
    a date that has passed or something a person raised."""
    if project.status in CLOSED:
        return []
    reasons = []
    if project.owner_id is None:
        reasons.append("no project owner")
    if project.target_date is not None and project.target_date < today:
        reasons.append(f"past its target date ({project.target_date.isoformat()})")
    late = [m for m in milestones if m.completed_at is None and m.due_date and m.due_date < today]
    if late:
        reasons.append(f"{len(late)} milestone{'s' if len(late) != 1 else ''} overdue")
    high = [r for r in risks if r.resolved_at is None and r.severity is RiskSeverity.HIGH]
    if high:
        reasons.append(f"{len(high)} high risk{'s' if len(high) != 1 else ''} open")
    if overdue_tasks:
        reasons.append(f"{overdue_tasks} overdue task{'s' if overdue_tasks != 1 else ''}")
    return reasons


def _base(user: User) -> Select[Any]:
    stmt = (
        select(Project, Account)
        .join(Account, Account.id == Project.account_id)
        .where(Project.deleted_at.is_(None), Account.deleted_at.is_(None))
    )
    clause = access.visible(user)
    return cast(Select[Any], stmt if clause is None else stmt.where(clause))


async def _views(db: AsyncSession, rows: list[Any]) -> list[ProjectView]:
    projects = [r[0] for r in rows]
    if not projects:
        return []
    ids = [p.id for p in projects]
    milestones: dict[uuid.UUID, list[Milestone]] = defaultdict(list)
    for m in (
        await db.execute(
            select(Milestone)
            .where(Milestone.project_id.in_(ids))
            .order_by(
                Milestone.position, Milestone.due_date.asc().nulls_last(), Milestone.created_at
            )
        )
    ).scalars():
        milestones[m.project_id].append(m)
    risks: dict[uuid.UUID, list[ProjectRisk]] = defaultdict(list)
    for r in (
        await db.execute(
            select(ProjectRisk)
            .where(ProjectRisk.project_id.in_(ids))
            .order_by(ProjectRisk.resolved_at.desc().nulls_first(), ProjectRisk.created_at.desc())
        )
    ).scalars():
        risks[r.project_id].append(r)
    start_of_today = datetime.combine(_today(), time.min, tzinfo=UTC)
    task_counts: dict[uuid.UUID, tuple[int, int]] = {}
    for project_id, open_count, overdue in (
        await db.execute(
            select(
                Task.project_id,
                func.count(),
                func.count().filter(Task.due_at < start_of_today),
            )
            .where(Task.project_id.in_(ids), Task.deleted_at.is_(None), Task.status.in_(OPEN_TASK))
            .group_by(Task.project_id)
        )
    ).all():
        if project_id is not None:
            task_counts[project_id] = (open_count, overdue)
    service_ids = {p.service_id for p in projects if p.service_id}
    services = (
        dict(
            (
                await db.execute(
                    select(Service.id, Service.name).where(Service.id.in_(service_ids))
                )
            ).all()
        )
        if service_ids
        else {}
    )
    owner_ids = {p.owner_id for p in projects if p.owner_id}
    names = (
        dict((await db.execute(select(User.id, User.name).where(User.id.in_(owner_ids)))).all())
        if owner_ids
        else {}
    )
    deal_ids = [p.deal_id for p in projects if p.deal_id]
    deals = (
        {d.id: d for d in (await db.execute(select(Deal).where(Deal.id.in_(deal_ids)))).scalars()}
        if deal_ids
        else {}
    )
    today = _today()
    views = []
    for project, account in rows:
        open_count, overdue = task_counts.get(project.id, (0, 0))
        views.append(
            ProjectView(
                project=project,
                account=account,
                service_name=services.get(project.service_id) if project.service_id else None,
                owner_name=names.get(project.owner_id) if project.owner_id else None,
                deal=deals.get(project.deal_id) if project.deal_id else None,
                milestones=milestones[project.id],
                risks=risks[project.id],
                open_tasks=open_count,
                overdue_tasks=overdue,
                attention=attention_reasons(
                    project, milestones[project.id], risks[project.id], overdue, today
                ),
            )
        )
    return views


async def list_projects(
    db: AsyncSession,
    *,
    user: User,
    status: str = "open",
    account_id: uuid.UUID | None = None,
    mine: bool = False,
    limit: int = 200,
) -> list[ProjectView]:
    stmt = _base(user)
    if status == "open":
        stmt = stmt.where(Project.status.not_in(CLOSED))
    elif status == "closed":
        stmt = stmt.where(Project.status.in_(CLOSED))
    elif status != "all":
        stmt = stmt.where(Project.status == ProjectStatus(status))
    if account_id is not None:
        stmt = stmt.where(Project.account_id == account_id)
    if mine:
        stmt = stmt.where(Project.owner_id == user.id)
    stmt = stmt.order_by(
        Project.target_date.asc().nulls_last(), Project.created_at.desc(), Project.id
    ).limit(limit)
    return await _views(db, list((await db.execute(stmt)).all()))


async def get_project(db: AsyncSession, *, user: User, project_id: uuid.UUID) -> ProjectView:
    row = (await db.execute(_base(user).where(Project.id == project_id))).first()
    if row is None:
        raise NotFound("Project not found.")
    return (await _views(db, [row]))[0]


# --- writing projects --------------------------------------------------------------------------


@dataclass
class NewMilestone:
    name: str
    due_date: date | None = None


@dataclass
class NewProject:
    name: str | None = None
    service_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    status: ProjectStatus = ProjectStatus.NOT_STARTED
    start_date: date | None = None
    target_date: date | None = None
    notes: str | None = None
    milestones: list[NewMilestone] = field(default_factory=list)


async def _visible_account(db: AsyncSession, user: User, account_id: uuid.UUID) -> Account:
    account = await db.get(Account, account_id, with_for_update=True)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")
    return account


async def _add_project(
    db: AsyncSession, *, user: User, account: Account, deal: Deal | None, data: NewProject
) -> Project:
    _check_dates(data.start_date, data.target_date)
    if data.status in CLOSED:
        raise ValidationFailed("A new project cannot start completed or cancelled.")
    service = await _service(db, data.service_id)
    owner = await _active_user(db, data.owner_id, "project owner")
    if deal is not None:
        existing = (
            await db.execute(
                select(Project.id).where(Project.deal_id == deal.id, Project.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise Conflict(
                "This deal already has a project.", details={"project_id": str(existing)}
            )
    name = (data.name or (deal.name if deal else "")).strip()[:200]
    if not name:
        raise ValidationFailed("A project needs a name.")
    project = Project(
        account_id=account.id,
        deal_id=deal.id if deal else None,
        name=name,
        service_id=service.id if service else None,
        owner_id=owner.id if owner else None,
        status=data.status,
        start_date=data.start_date,
        target_date=data.target_date,
        notes=(data.notes or "").strip() or None,
    )
    db.add(project)
    await db.flush()
    for position, m in enumerate(data.milestones):
        if m.name.strip():
            db.add(
                Milestone(
                    project_id=project.id,
                    name=m.name.strip()[:200],
                    due_date=m.due_date,
                    position=position,
                )
            )
    summary = f"Project started: {project.name}"
    if service:
        summary += f" ({service.name})"
    summary += f", owned by {owner.name if owner else 'nobody yet'}"
    if project.target_date:
        summary += f", due {project.target_date.isoformat()}"
    timeline.add(
        db,
        account_id=account.id,
        event_type="project.created",
        summary=summary + ".",
        actor_id=user.id,
        ref_table="projects",
        ref_id=project.id,
    )
    audit.record(
        db,
        action="project.created",
        object_table="projects",
        object_id=project.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            "account_id": str(account.id),
            "deal_id": _plain(project.deal_id),
            "name": project.name,
            "service_id": _plain(project.service_id),
            "owner_id": _plain(project.owner_id),
            "status": project.status.value,
            "start_date": _plain(project.start_date),
            "target_date": _plain(project.target_date),
            "milestones": len([m for m in data.milestones if m.name.strip()]),
        },
    )
    return project


async def create_project(
    db: AsyncSession,
    *,
    user: User,
    account_id: uuid.UUID,
    deal_id: uuid.UUID | None,
    data: NewProject,
) -> Project:
    """A project on an existing client. A prospect becomes a client by converting a won deal."""
    account = await _visible_account(db, user, account_id)
    if account.account_type is not AccountType.CUSTOMER:
        raise ValidationFailed(
            "Projects are for clients. Win a deal and convert it to start one.",
            code="not_a_client",
        )
    deal = None
    if deal_id is not None:
        deal = await db.get(Deal, deal_id)
        if deal is None or deal.deleted_at is not None or deal.account_id != account.id:
            raise ValidationFailed("That deal is not on this account.")
        if deal.outcome is not StageOutcome.WON:
            raise ValidationFailed("Only a won deal can have a project.", code="deal_not_won")
    project = await _add_project(db, user=user, account=account, deal=deal, data=data)
    await db.commit()
    return project


@dataclass
class Conversion:
    account: Account
    project: Project | None
    became_client: bool


async def convert(
    db: AsyncSession,
    *,
    user: User,
    deal_id: uuid.UUID,
    account_manager_id: uuid.UUID | None,
    project: NewProject | None,
    kickoff_task: bool = True,
) -> Conversion:
    """§14 Convert Opportunity → Client, from the won deal. The account keeps its identity and
    history; only its lifecycle state, account manager and (optionally) a project are added."""
    deal = await db.get(Deal, deal_id)
    if deal is None or deal.deleted_at is not None:
        raise NotFound("Deal not found.")
    account = await _visible_account(db, user, deal.account_id)
    if deal.outcome is not StageOutcome.WON:
        raise ValidationFailed("Only a won deal can be converted.", code="deal_not_won")
    if account.account_type in NOT_CONVERTIBLE:
        raise ValidationFailed(
            f"This account is marked {account.account_type.value} and cannot become a client.",
            code="not_convertible",
        )
    manager = await _active_user(db, account_manager_id, "account manager")

    became_client = account.account_type is not AccountType.CUSTOMER
    old = {
        "account_type": account.account_type.value,
        "account_manager_id": _plain(account.account_manager_id),
        "owner_id": _plain(account.owner_id),
        "client_since": _plain(account.client_since),
    }
    if became_client:
        account.account_type = AccountType.CUSTOMER
    if account.client_since is None:
        account.client_since = _today()
    if manager is not None:
        account.account_manager_id = manager.id
    if account.owner_id is None and deal.owner_id is not None:
        account.owner_id = deal.owner_id

    if became_client or manager is not None:
        summary = (
            f"Became a client after winning {deal.name}."
            if became_client
            else f"Won {deal.name} as an existing client."
        )
        if manager is not None:
            summary += f" Account manager: {manager.name}."
        timeline.add(
            db,
            account_id=account.id,
            event_type="account.converted",
            summary=summary,
            actor_id=user.id,
            ref_table="deals",
            ref_id=deal.id,
        )
        audit.record(
            db,
            action="account.converted",
            object_table="accounts",
            object_id=account.id,
            user_id=user.id,
            source=AuditSource.API,
            old_value=old,
            new_value={
                "account_type": account.account_type.value,
                "account_manager_id": _plain(account.account_manager_id),
                "owner_id": _plain(account.owner_id),
                "client_since": _plain(account.client_since),
                "deal_id": str(deal.id),
            },
        )

    created = None
    if project is not None:
        if project.service_id is None and deal.opportunity_id is not None:
            opportunity = await db.get(Opportunity, deal.opportunity_id)
            if opportunity is not None:
                project.service_id = opportunity.service_id
        if project.owner_id is None:
            project.owner_id = account_manager_id or deal.owner_id
        created = await _add_project(db, user=user, account=account, deal=deal, data=project)
        if kickoff_task:
            await crm.create_task(
                db,
                user=user,
                account_id=account.id,
                title=f"Kick off {created.name}",
                owner_id=created.owner_id,
                due_at=datetime.combine(created.start_date, time(9), tzinfo=UTC)
                if created.start_date
                else None,
                opportunity_id=None,
                description=None,
                project_id=created.id,
            )
    elif not became_client and manager is None:
        raise Conflict("This account is already a client. Start a project or set a manager.")
    await db.commit()
    return Conversion(account=account, project=created, became_client=became_client)


EDITABLE = ("name", "service_id", "owner_id", "status", "start_date", "target_date", "notes")


async def update_project(
    db: AsyncSession, *, user: User, project_id: uuid.UUID, changes: dict[str, Any]
) -> None:
    view = await get_project(db, user=user, project_id=project_id)
    project = view.project
    if "owner_id" in changes:
        await _active_user(db, changes["owner_id"], "project owner")
    if "service_id" in changes:
        await _service(db, changes["service_id"])
    if "notes" in changes:
        changes["notes"] = (changes["notes"] or "").strip() or None
    if "name" in changes:
        changes["name"] = changes["name"].strip()[:200]
    changed = {k: v for k, v in changes.items() if k in EDITABLE and getattr(project, k) != v}
    if not changed:
        return
    _check_dates(
        changed.get("start_date", project.start_date),
        changed.get("target_date", project.target_date),
    )
    old = {k: _plain(getattr(project, k)) for k in changed}
    old_status = project.status
    for key, value in changed.items():
        setattr(project, key, value)
    if "status" in changed:
        project.completed_on = _today() if project.status is ProjectStatus.COMPLETED else None
        timeline.add(
            db,
            account_id=project.account_id,
            event_type="project.status_changed",
            summary=f"Project {project.name}: {STATUS_LABELS[old_status]} to "
            f"{STATUS_LABELS[project.status]}.",
            actor_id=user.id,
            ref_table="projects",
            ref_id=project.id,
        )
    audit.record(
        db,
        action="project.updated",
        object_table="projects",
        object_id=project.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value=old,
        new_value={k: _plain(v) for k, v in changed.items()},
    )
    await db.commit()


# --- milestones and risks ----------------------------------------------------------------------


async def _milestone(
    db: AsyncSession, user: User, milestone_id: uuid.UUID
) -> tuple[Milestone, Project]:
    milestone = await db.get(Milestone, milestone_id)
    if milestone is None:
        raise NotFound("Milestone not found.")
    view = await get_project(db, user=user, project_id=milestone.project_id)
    return milestone, view.project


async def add_milestone(
    db: AsyncSession, *, user: User, project_id: uuid.UUID, name: str, due_date: date | None
) -> Milestone:
    view = await get_project(db, user=user, project_id=project_id)
    position = max((m.position for m in view.milestones), default=-1) + 1
    milestone = Milestone(
        project_id=project_id, name=name.strip()[:200], due_date=due_date, position=position
    )
    db.add(milestone)
    await db.flush()
    audit.record(
        db,
        action="milestone.created",
        object_table="milestones",
        object_id=milestone.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            "project_id": str(project_id),
            "name": milestone.name,
            "due_date": _plain(due_date),
        },
    )
    await db.commit()
    return milestone


async def update_milestone(
    db: AsyncSession, *, user: User, milestone_id: uuid.UUID, changes: dict[str, Any]
) -> None:
    milestone, project = await _milestone(db, user, milestone_id)
    old = {
        "name": milestone.name,
        "due_date": _plain(milestone.due_date),
        "done": milestone.completed_at is not None,
    }
    if "name" in changes:
        milestone.name = changes["name"].strip()[:200]
    if "due_date" in changes:
        milestone.due_date = changes["due_date"]
    if "done" in changes and changes["done"] != (milestone.completed_at is not None):
        if changes["done"]:
            milestone.completed_at = _now()
            milestone.completed_by_id = user.id
            timeline.add(
                db,
                account_id=project.account_id,
                event_type="milestone.completed",
                summary=f"Milestone reached on {project.name}: {milestone.name}.",
                actor_id=user.id,
                ref_table="projects",
                ref_id=project.id,
            )
        else:
            milestone.completed_at = None
            milestone.completed_by_id = None
    new = {
        "name": milestone.name,
        "due_date": _plain(milestone.due_date),
        "done": milestone.completed_at is not None,
    }
    if new == old:
        return
    audit.record(
        db,
        action="milestone.updated",
        object_table="milestones",
        object_id=milestone.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value=old,
        new_value=new,
    )
    await db.commit()


async def delete_milestone(db: AsyncSession, *, user: User, milestone_id: uuid.UUID) -> None:
    milestone, _project = await _milestone(db, user, milestone_id)
    audit.record(
        db,
        action="milestone.deleted",
        object_table="milestones",
        object_id=milestone.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value={"name": milestone.name, "due_date": _plain(milestone.due_date)},
    )
    await db.delete(milestone)
    await db.commit()


async def raise_risk(
    db: AsyncSession,
    *,
    user: User,
    project_id: uuid.UUID,
    description: str,
    severity: RiskSeverity,
) -> ProjectRisk:
    view = await get_project(db, user=user, project_id=project_id)
    risk = ProjectRisk(
        project_id=project_id,
        description=description.strip(),
        severity=severity,
        raised_by_id=user.id,
    )
    db.add(risk)
    await db.flush()
    timeline.add(
        db,
        account_id=view.project.account_id,
        event_type="project.risk_raised",
        summary=f"{severity.value.capitalize()} risk raised on {view.project.name}: "
        f"{risk.description[:200]}",
        actor_id=user.id,
        ref_table="projects",
        ref_id=project_id,
    )
    audit.record(
        db,
        action="project_risk.raised",
        object_table="project_risks",
        object_id=risk.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"project_id": str(project_id), "severity": severity.value},
    )
    await db.commit()
    return risk


async def update_risk(
    db: AsyncSession, *, user: User, risk_id: uuid.UUID, changes: dict[str, Any]
) -> None:
    risk = await db.get(ProjectRisk, risk_id)
    if risk is None:
        raise NotFound("Risk not found.")
    project = (await get_project(db, user=user, project_id=risk.project_id)).project
    old = {"severity": risk.severity.value, "resolved": risk.resolved_at is not None}
    if changes.get("severity") is not None:
        risk.severity = changes["severity"]
    if "resolved" in changes and changes["resolved"] != (risk.resolved_at is not None):
        if changes["resolved"]:
            risk.resolved_at = _now()
            risk.resolved_by_id = user.id
            risk.resolution = (changes.get("resolution") or "").strip() or None
            timeline.add(
                db,
                account_id=project.account_id,
                event_type="project.risk_resolved",
                summary=f"Risk resolved on {project.name}: {risk.description[:160]}"
                + (f" ({risk.resolution})" if risk.resolution else ""),
                actor_id=user.id,
                ref_table="projects",
                ref_id=project.id,
            )
        else:
            risk.resolved_at = None
            risk.resolved_by_id = None
            risk.resolution = None
    new = {"severity": risk.severity.value, "resolved": risk.resolved_at is not None}
    if new == old:
        return
    audit.record(
        db,
        action="project_risk.updated",
        object_table="project_risks",
        object_id=risk.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value=old,
        new_value=new,
        reason=risk.resolution,
    )
    await db.commit()


async def set_account_manager(
    db: AsyncSession, *, user: User, account_id: uuid.UUID, manager_id: uuid.UUID | None
) -> None:
    account = await _visible_account(db, user, account_id)
    manager = await _active_user(db, manager_id, "account manager")
    if account.account_manager_id == manager_id:
        return
    old = _plain(account.account_manager_id)
    account.account_manager_id = manager_id
    timeline.add(
        db,
        account_id=account.id,
        event_type="account.manager_changed",
        summary=f"Account manager: {manager.name if manager else 'nobody'}.",
        actor_id=user.id,
    )
    audit.record(
        db,
        action="account.manager_changed",
        object_table="accounts",
        object_id=account.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value={"account_manager_id": old},
        new_value={"account_manager_id": _plain(manager_id)},
    )
    await db.commit()
