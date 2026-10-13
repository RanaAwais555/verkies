"""/projects, /deals/{id}/convert and the account manager: client conversion and lightweight
project tracking (slice 4.1); /clients, client health, feedback and retention (slice 4.2);
expansion suggestions and referrals (slice 4.3)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from app.accounts.schemas import OwnerOut
from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.clients import expansion, health, referrals, service
from app.clients.health import ClientView
from app.clients.models import ClientFeedback, Milestone, ProjectRisk
from app.clients.service import NewMilestone, NewProject, ProjectView
from app.core.enums import HealthColour, ProjectStatus, ReferralStatus, RiskSeverity, Sentiment
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


# --- client health, feedback and retention (slice 4.2) -----------------------------------------

Manager = Annotated[User, Depends(require_permission("reports.team"))]


class ReasonOut(BaseModel):
    level: str
    text: str


class FeedbackOut(BaseModel):
    id: uuid.UUID
    sentiment: str
    note: str | None
    received_on: date
    project_id: uuid.UUID | None
    recorded_by: str | None
    created_at: datetime

    @classmethod
    def of(cls, f: ClientFeedback, names: dict[uuid.UUID, str]) -> "FeedbackOut":
        return cls(
            id=f.id,
            sentiment=f.sentiment.value,
            note=f.note,
            received_on=f.received_on,
            project_id=f.project_id,
            recorded_by=names.get(f.recorded_by_id) if f.recorded_by_id else None,
            created_at=f.created_at,
        )


class ClientOut(BaseModel):
    account_id: uuid.UUID
    name: str
    primary_domain: str | None
    account_manager: OwnerOut | None
    client_since: date | None
    health: str
    reasons: list[ReasonOut]
    last_contact_at: datetime | None
    open_projects: int
    latest_feedback: str | None
    latest_feedback_on: date | None
    expansion: list[str]

    @classmethod
    def of(cls, v: ClientView) -> "ClientOut":
        a, fb = v.account, v.facts.feedback
        return cls(
            account_id=a.id,
            name=a.name,
            primary_domain=a.primary_domain,
            account_manager=OwnerOut(id=a.account_manager_id, name=v.manager_name or "Unknown")
            if a.account_manager_id
            else None,
            client_since=a.client_since,
            health=v.colour.value,
            reasons=[ReasonOut(**r.as_dict()) for r in v.reasons],
            last_contact_at=v.facts.relationship.latest_interaction_at,
            open_projects=len(v.facts.projects),
            latest_feedback=fb.sentiment.value if fb else None,
            latest_feedback_on=fb.received_on if fb else None,
            expansion=v.expansion,
        )


class SnapshotOut(BaseModel):
    colour: str
    reasons: list[ReasonOut]
    assessed_at: datetime


class AccountHealthOut(BaseModel):
    current: ClientOut | None
    history: list[SnapshotOut]
    feedback: list[FeedbackOut]


class FeedbackIn(BaseModel):
    sentiment: Sentiment
    note: str | None = Field(default=None, max_length=4000)
    received_on: date | None = None
    project_id: uuid.UUID | None = None


class EndClientIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SweepOut(BaseModel):
    assessed: int
    changed: int
    risks_raised: int


@router.get("/clients")
async def list_clients(
    user: Member,
    db: DbSession,
    health_: Annotated[HealthColour | None, Query(alias="health")] = None,
    mine: bool = False,
    expansion_: Annotated[bool, Query(alias="expansion")] = False,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[ClientOut]:
    views = await health.list_clients(
        db, user=user, colour=health_, mine=mine, with_expansion=expansion_
    )
    # Ranked by health, which is worked out per client, so the cut comes after the ranking.
    return [ClientOut.of(v) for v in views[:limit]]


@router.post("/clients/health-check")
async def check_client_health(user: Manager, db: DbSession) -> SweepOut:
    """Run the retention engine now instead of waiting for the daily run."""
    done = await health.sweep(db)
    return SweepOut(assessed=done.assessed, changed=done.changed, risks_raised=done.risks_raised)


@router.get("/accounts/{account_id}/health")
async def account_health(account_id: uuid.UUID, user: Member, db: DbSession) -> AccountHealthOut:
    found = await health.account_health(db, user=user, account_id=account_id)
    return AccountHealthOut(
        current=ClientOut.of(found.current) if found.current else None,
        history=[
            SnapshotOut(
                colour=s.colour.value,
                reasons=[ReasonOut(**r) for r in s.reasons],
                assessed_at=s.assessed_at,
            )
            for s in found.history
        ],
        feedback=[FeedbackOut.of(f, found.recorded_by) for f in found.feedback],
    )


@router.post("/accounts/{account_id}/feedback", status_code=201)
async def record_feedback(
    account_id: uuid.UUID, body: FeedbackIn, user: Member, db: DbSession
) -> FeedbackOut:
    feedback = await health.record_feedback(
        db,
        user=user,
        account_id=account_id,
        sentiment=body.sentiment,
        note=body.note,
        received_on=body.received_on,
        project_id=body.project_id,
    )
    await db.refresh(feedback)
    return FeedbackOut.of(feedback, {user.id: user.name})


@router.post("/accounts/{account_id}/end-client", status_code=204)
async def end_client(
    account_id: uuid.UUID, body: EndClientIn, user: Member, db: DbSession
) -> Response:
    await health.end_client(db, user=user, account_id=account_id, reason=body.reason)
    return Response(status_code=204)


# --- expansion and referrals (slice 4.3) -------------------------------------------------------


class EvidenceOut(BaseModel):
    id: uuid.UUID
    source_url: str
    evidence_text: str
    collected_at: datetime


class ServiceRefOut(BaseModel):
    id: uuid.UUID
    name: str


class SuggestionOut(BaseModel):
    candidate_id: uuid.UUID
    category_key: str
    category_name: str
    title: str
    problem: str
    confidence: float
    found_at: datetime
    services: list[ServiceRefOut]
    evidence: list[EvidenceOut]
    dismissed_before: bool

    @classmethod
    def of(cls, s: expansion.Suggestion) -> "SuggestionOut":
        return cls(
            candidate_id=s.candidate.id,
            category_key=s.category.key,
            category_name=s.category.name,
            title=s.candidate.title,
            problem=s.candidate.problem_statement,
            confidence=float(s.candidate.confidence),
            found_at=s.found_at,
            services=[ServiceRefOut(id=x.id, name=x.name) for x in s.services],
            evidence=[
                EvidenceOut(
                    id=e.id,
                    source_url=e.source_url,
                    evidence_text=e.evidence_text[:500],
                    collected_at=e.collected_at,
                )
                for e in s.evidence[:5]
            ],
            dismissed_before=s.dismissed_before,
        )


class OpenSuggestionIn(BaseModel):
    service_id: uuid.UUID | None = None


class OpenedOut(BaseModel):
    opportunity_id: uuid.UUID


class DismissIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.get("/accounts/{account_id}/expansion")
async def expansion_suggestions(
    account_id: uuid.UUID, user: Member, db: DbSession
) -> list[SuggestionOut]:
    return [
        SuggestionOut.of(s)
        for s in await expansion.for_account(db, user=user, account_id=account_id)
    ]


@router.post("/accounts/{account_id}/expansion/{candidate_id}/open", status_code=201)
async def open_suggestion(
    account_id: uuid.UUID,
    candidate_id: uuid.UUID,
    body: OpenSuggestionIn,
    user: Member,
    db: DbSession,
) -> OpenedOut:
    opportunity = await expansion.open_suggestion(
        db, user=user, account_id=account_id, candidate_id=candidate_id, service_id=body.service_id
    )
    return OpenedOut(opportunity_id=opportunity.id)


@router.post("/accounts/{account_id}/expansion/{candidate_id}/dismiss", status_code=204)
async def dismiss_suggestion(
    account_id: uuid.UUID, candidate_id: uuid.UUID, body: DismissIn, user: Member, db: DbSession
) -> Response:
    await expansion.dismiss_suggestion(
        db, user=user, account_id=account_id, candidate_id=candidate_id, reason=body.reason
    )
    return Response(status_code=204)


class MoneyOut(BaseModel):
    amount: float
    currency: str


class AccountRefOut(BaseModel):
    id: uuid.UUID
    name: str


class ReferralOut(BaseModel):
    id: uuid.UUID
    referrer_name: str
    referrer_account: AccountRefOut | None
    relationship: str | None
    referred_company: str
    referred_domain: str | None
    referred_account: AccountRefOut | None
    status: str
    converted: bool
    won_deals: int
    revenue: list[MoneyOut]
    unknown_value_deals: int
    notes: str | None
    received_on: date
    recorded_by: str | None

    @classmethod
    def of(cls, v: referrals.ReferralView) -> "ReferralOut":
        r = v.referral
        return cls(
            id=r.id,
            referrer_name=r.referrer_name,
            referrer_account=AccountRefOut(id=v.referrer.id, name=v.referrer.name)
            if v.referrer
            else None,
            relationship=r.relationship,
            referred_company=r.referred_company,
            referred_domain=r.referred_domain,
            referred_account=AccountRefOut(id=v.referred.id, name=v.referred.name)
            if v.referred
            else None,
            status=r.status.value,
            converted=v.converted,
            won_deals=v.won_deals,
            revenue=[MoneyOut(amount=float(a), currency=c) for c, a in sorted(v.revenue.items())],
            unknown_value_deals=v.unknown_value_deals,
            notes=r.notes,
            received_on=r.received_on,
            recorded_by=v.recorded_by,
        )


class ReferralIn(BaseModel):
    referred_company: str = Field(min_length=1, max_length=300)
    referred_domain: str | None = Field(default=None, max_length=300)
    referrer_account_id: uuid.UUID | None = None
    referrer_contact_id: uuid.UUID | None = None
    referrer_name: str | None = Field(default=None, max_length=200)
    relationship: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    received_on: date | None = None


class UpdateReferral(BaseModel):
    status: ReferralStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)
    relationship: str | None = Field(default=None, max_length=120)
    referred_company: str | None = Field(default=None, min_length=1, max_length=300)
    referred_domain: str | None = Field(default=None, max_length=300)


@router.get("/referrals")
async def list_referrals(
    user: Member, db: DbSession, account_id: uuid.UUID | None = None
) -> list[ReferralOut]:
    views = await referrals.list_referrals(db, user=user, account_id=account_id)
    return [ReferralOut.of(v) for v in views]


@router.post("/referrals", status_code=201)
async def create_referral(body: ReferralIn, user: Member, db: DbSession) -> ReferralOut:
    referral = await referrals.create_referral(
        db, user=user, data=referrals.NewReferral(**body.model_dump())
    )
    return ReferralOut.of(await referrals.get_referral(db, user=user, referral_id=referral.id))


@router.patch("/referrals/{referral_id}")
async def update_referral(
    referral_id: uuid.UUID, body: UpdateReferral, user: Member, db: DbSession
) -> ReferralOut:
    changes = body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] is None:
        raise ValidationFailed("A referral needs a status.")
    await referrals.update_referral(db, user=user, referral_id=referral_id, changes=changes)
    return ReferralOut.of(await referrals.get_referral(db, user=user, referral_id=referral_id))
