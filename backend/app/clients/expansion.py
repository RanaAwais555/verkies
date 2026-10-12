"""The expansion engine (master context §11 land and expand, §14; slice 4.3).

Every suggestion is a problem research found on the client's own website, with the evidence it
was found from: the opportunity candidates of the client's completed research runs. A suggestion
is left out when the client already has an opportunity for that category (open, won or lost) or
when someone has opened or dismissed it; a dismissed suggestion returns only when a research run
newer than the dismissal finds the problem again. The services offered for a suggestion are the
confirmed catalogue services that answer its category. Nothing is invented: a client with no
research has no suggestions, and the screen says to research the website again.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account
from app.audit import service as audit
from app.auth.models import User
from app.catalogue.models import Service
from app.clients.models import ExpansionOpportunity
from app.core.enums import AccountType, AuditSource, ExpansionDecision, JobStatus
from app.core.errors import NotFound, ValidationFailed
from app.crm import timeline
from app.crm.models import Opportunity
from app.evidence.models import Evidence
from app.opportunities.models import (
    OpportunityCandidate,
    OpportunityCategory,
    opportunity_candidate_evidence,
)
from app.research.models import ResearchRun


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Suggestion:
    account_id: uuid.UUID
    candidate: OpportunityCandidate
    category: OpportunityCategory
    found_at: datetime  # when the research that found it finished
    services: list[Service] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    dismissed_before: bool = False


async def suggestions_for(
    db: AsyncSession, account_ids: list[uuid.UUID], *, with_evidence: bool = True
) -> dict[uuid.UUID, list[Suggestion]]:
    """Current expansion suggestions per client account, strongest first."""
    out: dict[uuid.UUID, list[Suggestion]] = defaultdict(list)
    if not account_ids:
        return out
    rows = (
        await db.execute(
            select(OpportunityCandidate, OpportunityCategory, ResearchRun)
            .join(OpportunityCategory, OpportunityCategory.id == OpportunityCandidate.category_id)
            .join(ResearchRun, ResearchRun.id == OpportunityCandidate.research_run_id)
            .where(
                ResearchRun.account_id.in_(account_ids),
                ResearchRun.status == JobStatus.COMPLETED,
                OpportunityCategory.is_active,
            )
            .order_by(
                ResearchRun.finished_at.desc().nulls_last(),
                OpportunityCandidate.confidence.desc(),
                OpportunityCandidate.created_at,
            )
        )
    ).all()
    # The latest finding per account and category.
    latest: dict[tuple[uuid.UUID, uuid.UUID], tuple[Any, Any, Any]] = {}
    for candidate, category, run in rows:
        if run.account_id is not None:
            latest.setdefault((run.account_id, category.id), (candidate, category, run))
    if not latest:
        return out

    taken = {
        (a, c)
        for a, c in (
            await db.execute(
                select(Opportunity.account_id, Opportunity.category_id).where(
                    Opportunity.account_id.in_(account_ids),
                    Opportunity.deleted_at.is_(None),
                    Opportunity.category_id.is_not(None),
                )
            )
        ).all()
    }
    decisions = {
        (d.account_id, d.category_id): d
        for d in (
            await db.execute(
                select(ExpansionOpportunity).where(ExpansionOpportunity.account_id.in_(account_ids))
            )
        ).scalars()
    }
    services = list(
        (
            await db.execute(
                select(Service).where(Service.confirmed, Service.is_active).order_by(Service.name)
            )
        ).scalars()
    )
    found: list[Suggestion] = []
    for (account_id, category_id), (candidate, category, run) in latest.items():
        if (account_id, category_id) in taken:
            continue
        found_at = run.finished_at or run.created_at
        decision = decisions.get((account_id, category_id))
        if decision is not None and (
            decision.decision is ExpansionDecision.OPENED or found_at <= decision.decided_at
        ):
            continue
        found.append(
            Suggestion(
                account_id=account_id,
                candidate=candidate,
                category=category,
                found_at=found_at,
                services=[s for s in services if category.key in (s.solves or [])],
                dismissed_before=decision is not None,
            )
        )
    if with_evidence and found:
        by_candidate = {s.candidate.id: s for s in found}
        for candidate_id, evidence in (
            await db.execute(
                select(opportunity_candidate_evidence.c.candidate_id, Evidence)
                .join(Evidence, Evidence.id == opportunity_candidate_evidence.c.evidence_id)
                .where(opportunity_candidate_evidence.c.candidate_id.in_(list(by_candidate)))
                .order_by(Evidence.confidence.desc(), Evidence.collected_at.desc())
            )
        ).all():
            by_candidate[candidate_id].evidence.append(evidence)
    for s in sorted(found, key=lambda s: (-s.candidate.confidence, s.category.name)):
        out[s.account_id].append(s)
    return out


async def _client(db: AsyncSession, user: User, account_id: uuid.UUID) -> Account:
    account = await db.get(Account, account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")
    return account


async def for_account(db: AsyncSession, *, user: User, account_id: uuid.UUID) -> list[Suggestion]:
    account = await _client(db, user, account_id)
    if account.account_type is not AccountType.CUSTOMER:
        return []
    return (await suggestions_for(db, [account.id]))[account.id]


async def _suggestion(
    db: AsyncSession, user: User, account_id: uuid.UUID, candidate_id: uuid.UUID
) -> tuple[Account, Suggestion]:
    account = await _client(db, user, account_id)
    if account.account_type is not AccountType.CUSTOMER:
        raise ValidationFailed("Expansion is for clients.", code="not_a_client")
    current = (await suggestions_for(db, [account.id]))[account.id]
    found = next((s for s in current if s.candidate.id == candidate_id), None)
    if found is None:
        raise NotFound("That is not a current expansion suggestion for this client.")
    return account, found


async def _decide(
    db: AsyncSession,
    *,
    user: User,
    account: Account,
    suggestion: Suggestion,
    decision: ExpansionDecision,
    service_id: uuid.UUID | None,
    opportunity_id: uuid.UUID | None,
    reason: str | None,
) -> ExpansionOpportunity:
    row = (
        await db.execute(
            select(ExpansionOpportunity).where(
                ExpansionOpportunity.account_id == account.id,
                ExpansionOpportunity.category_id == suggestion.category.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = ExpansionOpportunity(account_id=account.id, category_id=suggestion.category.id)
        db.add(row)
    row.candidate_id = suggestion.candidate.id
    row.decision = decision
    row.service_id = service_id
    row.opportunity_id = opportunity_id
    row.reason = reason
    row.decided_by_id = user.id
    row.decided_at = _now()
    await db.flush()
    return row


async def open_suggestion(
    db: AsyncSession,
    *,
    user: User,
    account_id: uuid.UUID,
    candidate_id: uuid.UUID,
    service_id: uuid.UUID | None,
) -> Opportunity:
    """Make a suggestion an opportunity on the client, ready for an expansion-pipeline deal."""
    account, suggestion = await _suggestion(db, user, account_id, candidate_id)
    if service_id is not None and service_id not in {s.id for s in suggestion.services}:
        raise ValidationFailed("That service does not answer this problem.", code="invalid_service")
    if service_id is None and len(suggestion.services) == 1:
        service_id = suggestion.services[0].id
    opportunity = Opportunity(
        account_id=account.id,
        name=f"Expansion: {suggestion.category.name} for {account.name}"[:200],
        problem=suggestion.candidate.problem_statement,
        category_id=suggestion.category.id,
        service_id=service_id,
        owner_id=account.account_manager_id or account.owner_id or user.id,
    )
    db.add(opportunity)
    await db.flush()
    row = await _decide(
        db,
        user=user,
        account=account,
        suggestion=suggestion,
        decision=ExpansionDecision.OPENED,
        service_id=service_id,
        opportunity_id=opportunity.id,
        reason=None,
    )
    timeline.add(
        db,
        account_id=account.id,
        event_type="expansion.opened",
        summary=f"Expansion opportunity opened: {suggestion.category.name}. "
        f"{suggestion.candidate.problem_statement[:200]}",
        actor_id=user.id,
        ref_table="opportunities",
        ref_id=opportunity.id,
    )
    audit.record(
        db,
        action="expansion.opened",
        object_table="expansion_opportunities",
        object_id=row.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            "account_id": str(account.id),
            "category": suggestion.category.key,
            "candidate_id": str(suggestion.candidate.id),
            "opportunity_id": str(opportunity.id),
            "service_id": str(service_id) if service_id else None,
            "evidence": [str(e.id) for e in suggestion.evidence],
        },
    )
    await db.commit()
    return opportunity


async def dismiss_suggestion(
    db: AsyncSession, *, user: User, account_id: uuid.UUID, candidate_id: uuid.UUID, reason: str
) -> None:
    account, suggestion = await _suggestion(db, user, account_id, candidate_id)
    row = await _decide(
        db,
        user=user,
        account=account,
        suggestion=suggestion,
        decision=ExpansionDecision.DISMISSED,
        service_id=None,
        opportunity_id=None,
        reason=reason.strip(),
    )
    timeline.add(
        db,
        account_id=account.id,
        event_type="expansion.dismissed",
        summary=f"Expansion suggestion dismissed: {suggestion.category.name} ({reason.strip()}).",
        actor_id=user.id,
    )
    audit.record(
        db,
        action="expansion.dismissed",
        object_table="expansion_opportunities",
        object_id=row.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"category": suggestion.category.key, "candidate_id": str(candidate_id)},
        reason=reason.strip(),
    )
    await db.commit()
