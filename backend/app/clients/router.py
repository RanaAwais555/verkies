"""/projects, /deals/{id}/convert and the account manager: client conversion and lightweight
project tracking (slice 4.1)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from app.accounts.schemas import OwnerOut
from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.clients import service
from app.clients.models import Milestone, ProjectRisk
from app.clients.service import NewMilestone, NewProject, ProjectView
from app.core.enums import ProjectStatus, RiskSeverity
from app.core.errors import ValidationFailed
from app.crm.schemas import TaskOut
from app.crm.service import list_tasks_for_project

router = APIRouter(tags=["clients"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]


class MilestoneOut(BaseModel):
    id: uuid.UUID
    name: str
    due_date: date | None
    done: bool
    completed_at: datetime | None
    overdue: bool

    @classmethod
    def of(cls, m: Milestone, today: date) -> "MilestoneOut":
        return cls(
            id=m.id,
            name=m.name,
            due_date=m.due_date,
            done=m.completed_at is not None,
            completed_at=m.completed_at,
            overdue=m.completed_at is None and m.due_date is not None and m.due_date < today,
        )


class RiskOut(BaseModel):
    id: uuid.UUID
    description: str
    severity: str
    resolved: bool
    resolved_at: datetime | None
    resolution: str | None
    created_at: datetime

    @classmethod
    def of(cls, r: ProjectRisk) -> "RiskOut":
        return cls(
            id=r.id,
            description=r.description,
            severity=r.severity.value,
            resolved=r.resolved_at is not None,
            resolved_at=r.resolved_at,
            resolution=r.resolution,
            created_at=r.created_at,
        )


class DealRefOut(BaseModel):
    id: uuid.UUID
    name: str
    value: float | None
    currency: str
    closed_at: datetime | None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    account_id: uuid.UUID
    account_name: str
    deal: DealRefOut | None
    service_id: uuid.UUID | None
    service_name: str | None
    owner: OwnerOut | None
    status: str
    start_date: date | None
    target_date: date | None
    completed_on: date | None
    notes: str | None
    milestones: list[MilestoneOut]
    milestones_done: int
    open_risks: int
    open_tasks: int
    overdue_tasks: int
    requires_attention: list[str]
    created_at: datetime

    @classmethod
    def of(cls, v: ProjectView) -> "ProjectOut":
        p, today = v.project, service._today()
        return cls(
            id=p.id,
            name=p.name,
            account_id=v.account.id,
            account_name=v.account.name,
            deal=DealRefOut(
                id=v.deal.id,
                name=v.deal.name,
                value=float(v.deal.value) if v.deal.value is not None else None,
                currency=v.deal.currency,
                closed_at=v.deal.closed_at,
            )
            if v.deal
            else None,
            service_id=p.service_id,
            service_name=v.service_name,
            owner=OwnerOut(id=p.owner_id, name=v.owner_name or "Unknown") if p.owner_id else None,
            status=p.status.value,
            start_date=p.start_date,
            target_date=p.target_date,
            completed_on=p.completed_on,
            notes=p.notes,
            milestones=[MilestoneOut.of(m, today) for m in v.milestones],
            milestones_done=sum(1 for m in v.milestones if m.completed_at is not None),
            open_risks=sum(1 for r in v.risks if r.resolved_at is None),
            open_tasks=v.open_tasks,
            overdue_tasks=v.overdue_tasks,
            requires_attention=v.attention,
            created_at=p.created_at,
        )


class ProjectDetailOut(ProjectOut):
    risks: list[RiskOut]
    tasks: list[TaskOut]


class MilestoneIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    due_date: date | None = None


class ProjectIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    service_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    status: ProjectStatus = ProjectStatus.NOT_STARTED
    start_date: date | None = None
    target_date: date | None = None
    notes: str | None = Field(default=None, max_length=10000)
    milestones: list[MilestoneIn] = Field(default_factory=list, max_length=50)

    def as_new(self) -> NewProject:
        return NewProject(
            name=self.name,
            service_id=self.service_id,
            owner_id=self.owner_id,
            status=self.status,
            start_date=self.start_date,
            target_date=self.target_date,
            notes=self.notes,
            milestones=[NewMilestone(name=m.name, due_date=m.due_date) for m in self.milestones],
        )


class CreateProject(ProjectIn):
    account_id: uuid.UUID
    deal_id: uuid.UUID | None = None


class ConvertDeal(BaseModel):
    account_manager_id: uuid.UUID | None = None
    # Leave out to convert without starting a project.
    project: ProjectIn | None = None
    kickoff_task: bool = True


class ConversionOut(BaseModel):
    account_id: uuid.UUID
    account_type: str
    became_client: bool
    project_id: uuid.UUID | None


class UpdateProject(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    service_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    status: ProjectStatus | None = None
    start_date: date | None = None
    target_date: date | None = None
    notes: str | None = Field(default=None, max_length=10000)


class UpdateMilestone(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    due_date: date | None = None
    done: bool | None = None


class RiskIn(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    severity: RiskSeverity = RiskSeverity.MEDIUM


class UpdateRisk(BaseModel):
    severity: RiskSeverity | None = None
    resolved: bool | None = None
    resolution: str | None = Field(default=None, max_length=2000)


class AccountManagerIn(BaseModel):
    account_manager_id: uuid.UUID | None


async def _detail(db: DbSession, user: User, project_id: uuid.UUID) -> ProjectDetailOut:
    view = await service.get_project(db, user=user, project_id=project_id)
    tasks = await list_tasks_for_project(db, project_id)
    return ProjectDetailOut(
        **ProjectOut.of(view).model_dump(),
        risks=[RiskOut.of(r) for r in view.risks],
        tasks=[TaskOut.of(t, account_name=view.account.name, owner_name=n) for t, n in tasks],
    )


@router.post("/deals/{deal_id}/convert")
async def convert_deal(
    deal_id: uuid.UUID, body: ConvertDeal, user: Member, db: DbSession
) -> ConversionOut:
    done = await service.convert(
        db,
        user=user,
        deal_id=deal_id,
        account_manager_id=body.account_manager_id,
        project=body.project.as_new() if body.project else None,
        kickoff_task=body.kickoff_task,
    )
    return ConversionOut(
        account_id=done.account.id,
        account_type=done.account.account_type.value,
        became_client=done.became_client,
        project_id=done.project.id if done.project else None,
    )


@router.put("/accounts/{account_id}/account-manager", status_code=204)
async def set_account_manager(
    account_id: uuid.UUID, body: AccountManagerIn, user: Member, db: DbSession
) -> Response:
    await service.set_account_manager(
        db, user=user, account_id=account_id, manager_id=body.account_manager_id
    )
    return Response(status_code=204)


@router.get("/projects")
async def list_projects(
    user: Member,
    db: DbSession,
    status: Literal[
        "open",
        "closed",
        "all",
        "not_started",
        "planning",
        "active",
        "at_risk",
        "on_hold",
        "completed",
        "cancelled",
    ] = "open",
    account_id: uuid.UUID | None = None,
    mine: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[ProjectOut]:
    views = await service.list_projects(
        db, user=user, status=status, account_id=account_id, mine=mine, limit=limit
    )
    return [ProjectOut.of(v) for v in views]


@router.post("/projects", status_code=201)
async def create_project(body: CreateProject, user: Member, db: DbSession) -> ProjectDetailOut:
    project = await service.create_project(
        db, user=user, account_id=body.account_id, deal_id=body.deal_id, data=body.as_new()
    )
    return await _detail(db, user, project.id)


@router.get("/projects/{project_id}")
async def get_project(project_id: uuid.UUID, user: Member, db: DbSession) -> ProjectDetailOut:
    return await _detail(db, user, project_id)


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: uuid.UUID, body: UpdateProject, user: Member, db: DbSession
) -> ProjectDetailOut:
    changes = body.model_dump(exclude_unset=True)
    for required in ("name", "status"):
        if required in changes and changes[required] is None:
            raise ValidationFailed(f"A project needs a {required}.")
    if not changes:
        raise ValidationFailed("Nothing to change.")
    await service.update_project(db, user=user, project_id=project_id, changes=changes)
    return await _detail(db, user, project_id)


@router.post("/projects/{project_id}/milestones", status_code=201)
async def add_milestone(
    project_id: uuid.UUID, body: MilestoneIn, user: Member, db: DbSession
) -> ProjectDetailOut:
    await service.add_milestone(
        db, user=user, project_id=project_id, name=body.name, due_date=body.due_date
    )
    return await _detail(db, user, project_id)


@router.patch("/milestones/{milestone_id}")
async def update_milestone(
    milestone_id: uuid.UUID, body: UpdateMilestone, user: Member, db: DbSession
) -> MilestoneOut:
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise ValidationFailed("A milestone needs a name.")
    if changes.get("done", False) is None:
        raise ValidationFailed("Say whether the milestone is done.")
    await service.update_milestone(db, user=user, milestone_id=milestone_id, changes=changes)
    milestone = await db.get(Milestone, milestone_id)
    assert milestone is not None
    await db.refresh(milestone)
    return MilestoneOut.of(milestone, service._today())


@router.delete("/milestones/{milestone_id}", status_code=204)
async def delete_milestone(milestone_id: uuid.UUID, user: Member, db: DbSession) -> Response:
    await service.delete_milestone(db, user=user, milestone_id=milestone_id)
    return Response(status_code=204)


@router.post("/projects/{project_id}/risks", status_code=201)
async def raise_risk(project_id: uuid.UUID, body: RiskIn, user: Member, db: DbSession) -> RiskOut:
    risk = await service.raise_risk(
        db, user=user, project_id=project_id, description=body.description, severity=body.severity
    )
    await db.refresh(risk)
    return RiskOut.of(risk)


@router.patch("/risks/{risk_id}")
async def update_risk(risk_id: uuid.UUID, body: UpdateRisk, user: Member, db: DbSession) -> RiskOut:
    await service.update_risk(
        db, user=user, risk_id=risk_id, changes=body.model_dump(exclude_unset=True)
    )
    risk = await db.get(ProjectRisk, risk_id)
    assert risk is not None
    await db.refresh(risk)
    return RiskOut.of(risk)
