"""Account list and Account 360 API models."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.accounts.models import Account, Contact
from app.crm.schemas import OpportunityOut, TaskOut
from app.research.models import ResearchRun

SCORES = (
    "icp_score",
    "opportunity_score",
    "intent_score",
    "buyer_confidence",
    "data_confidence",
    "service_fit",
    "timing_score",
    "commercial_potential",
    "client_similarity",
    "evidence_strength",
)


def as_float(value: Any) -> float | None:
    return None if value is None else float(value)


class OwnerOut(BaseModel):
    id: uuid.UUID
    name: str


def owner_of(owner_id: uuid.UUID | None, names: dict[uuid.UUID, str]) -> OwnerOut | None:
    if owner_id is None:
        return None
    return OwnerOut(id=owner_id, name=names.get(owner_id, "Unknown"))


class AccountSummaryOut(BaseModel):
    id: uuid.UUID
    name: str
    primary_domain: str | None
    account_type: str
    industry: str | None
    hq_country: str | None
    owner: OwnerOut | None
    priority_score: float | None
    priority_band: str | None
    next_activity_at: datetime | None
    last_activity_at: datetime | None
    open_tasks: int
    created_at: datetime

    @classmethod
    def of(cls, a: Account, names: dict[uuid.UUID, str], open_tasks: int) -> "AccountSummaryOut":
        return cls(
            id=a.id,
            name=a.name,
            primary_domain=a.primary_domain,
            account_type=a.account_type.value,
            industry=a.industry,
            hq_country=a.hq_country,
            owner=owner_of(a.owner_id, names),
            priority_score=as_float(a.priority_score),
            priority_band=a.priority_band.value if a.priority_band else None,
            next_activity_at=a.next_activity_at,
            last_activity_at=a.last_activity_at,
            open_tasks=open_tasks,
            created_at=a.created_at,
        )


class LeadOut(BaseModel):
    id: uuid.UUID
    research_run_id: uuid.UUID | None
    source: str
    status: str
    owner: OwnerOut | None
    priority_score: float | None
    priority_band: str | None
    qualified_at: datetime | None
    created_at: datetime


class ContactOut(BaseModel):
    id: uuid.UUID
    name: str
    title: str | None
    email: str | None
    phone: str | None
    decision_maker_role: str | None
    verification_status: str
    source: str
    source_url: str | None
    collected_at: datetime
    confidence: float

    @classmethod
    def of(cls, c: Contact) -> "ContactOut":
        return cls(
            id=c.id,
            name=c.name,
            title=c.title,
            email=c.email,
            phone=c.phone,
            decision_maker_role=c.decision_maker_role.value if c.decision_maker_role else None,
            verification_status=c.verification_status.value,
            source=c.source,
            source_url=c.source_url,
            collected_at=c.collected_at,
            confidence=float(c.confidence),
        )


class RunSummaryOut(BaseModel):
    id: uuid.UUID
    normalised_domain: str
    status: str
    review_status: str
    created_at: datetime
    finished_at: datetime | None

    @classmethod
    def of(cls, r: ResearchRun) -> "RunSummaryOut":
        return cls(
            id=r.id,
            normalised_domain=r.normalised_domain,
            status=r.status.value,
            review_status=r.review_status.value,
            created_at=r.created_at,
            finished_at=r.finished_at,
        )


class Account360Out(AccountSummaryOut):
    legal_name: str | None
    website_url: str | None
    description: str | None
    hq_city: str | None
    source: str | None
    linkedin_company_url: str | None
    domains: list[str]
    # All ten dimensions; null means Unknown, never zero.
    scores: dict[str, float | None]
    leads: list[LeadOut]
    opportunities: list[OpportunityOut]
    contacts: list[ContactOut]
    tasks: list[TaskOut]
    research_runs: list[RunSummaryOut]
    latest_brief_run_id: uuid.UUID | None


class TimelineEventOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    event_type: str
    summary: str
    ref_table: str | None
    ref_id: uuid.UUID | None
    actor: OwnerOut | None
