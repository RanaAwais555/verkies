"""The review queue and the approve/reject decision (PRODUCT_SPEC.md §3, DATA_MODEL.md §3).

Approval creates (or reuses) the Account, and creates the Lead, Opportunity, Contacts and the
next-action Task, attaches the run's evidence to the Account and writes the timeline, all in
the caller's transaction: either everything commits or nothing does.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account, AccountDomain, AccountIdentifier, Contact, Suppression
from app.audit import service as audit
from app.auth.models import User
from app.briefs.models import LeadBrief
from app.catalogue.models import ServiceMatch
from app.config import Settings
from app.core.enums import (
    AccountType,
    AuditSource,
    DecisionMakerRole,
    JobStatus,
    LeadStatus,
    PriorityBand,
    RejectionReason,
    ReviewStatus,
    ServiceSlot,
    SuppressionKind,
    TaskPriority,
)
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.crm import timeline
from app.crm.models import Lead, Opportunity, Task
from app.evidence.models import Claim, Evidence, Observation
from app.intelligence.facts import Facts
from app.intelligence.people import named_people, same_person
from app.opportunities.models import OpportunityCandidate, OpportunityCategory
from app.qualification.models import QualificationResult
from app.research.models import ResearchRun
from app.scoring import stage as scoring
from app.scoring.models import ScoreSnapshot

NAME_SIMILARITY = 0.6  # pg_trgm similarity that counts as a possible duplicate (§16)
QUEUE_LIMIT = 200
SCORE_FIELDS = (
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
TASK_PRIORITY = {
    PriorityBand.HOT: TaskPriority.URGENT,
    PriorityBand.HIGH: TaskPriority.HIGH,
}
# Title keywords -> buying role. First match wins; no match leaves the role Unknown.
ROLE_RULES: tuple[tuple[re.Pattern[str], DecisionMakerRole], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), role)
    for pattern, role in (
        (
            r"\b(cto|technical|technology|engineering|it director|head of it)\b",
            DecisionMakerRole.TECHNICAL_BUYER,
        ),
        (
            r"\b(founder|co-founder|owner|ceo|chief executive|managing director|managing partner"
            r"|principal|president|director|partner)\b",
            DecisionMakerRole.DECISION_MAKER,
        ),
        (r"\b(cmo|marketing|growth|brand)\b", DecisionMakerRole.MARKETING_BUYER),
        (r"\b(coo|operations|ops)\b", DecisionMakerRole.OPERATIONS_BUYER),
        (r"\b(cpo|product)\b", DecisionMakerRole.PRODUCT_BUYER),
        (r"\b(procurement|purchasing)\b", DecisionMakerRole.PROCUREMENT),
    )
)
ISO2 = re.compile(r"^[A-Z]{2}$")


def _now() -> datetime:
    return datetime.now(UTC)


def add_business_days(start: datetime, days: int) -> datetime:
    result = start
    while days > 0:
        result += timedelta(days=1)
        if result.weekday() < 5:
            days -= 1
    while result.weekday() >= 5:  # due on a weekend (days == 0 from a weekend) -> Monday
        result += timedelta(days=1)
    return result


def role_for(title: str | None) -> DecisionMakerRole | None:
    for pattern, role in ROLE_RULES:
        if title and pattern.search(title):
            return role
    return None


# --- the queue -------------------------------------------------------------------------------


@dataclass
class QueueItem:
    run: ResearchRun
    summary: dict[str, Any]
    hard_reject: bool
    recommended_rejection: RejectionReason | None
    explanation: str
    next_action: str | None
    possible_duplicates: list[dict[str, Any]] = field(default_factory=list)


def _current_brief(run: ResearchRun, brief: LeadBrief | None) -> LeadBrief | None:
    if brief is None or brief.generated_by.get("attempt") != run.retry_count:
        return None
    return brief


def next_action_text(brief: LeadBrief) -> str | None:
    section = brief.sections.get("next_action") or {}
    claims = section.get("claims") or []
    if claims:
        return str(claims[0]["text"])
    unknown = section.get("unknown")
    return str(unknown) if unknown else None


async def queue(db: AsyncSession) -> list[QueueItem]:
    """Completed runs awaiting a decision: qualifying prospects first, then by priority.
    Rejected and approved runs are never in the queue (they stay searchable as runs)."""
    rows = (
        await db.execute(
            select(ResearchRun, LeadBrief, QualificationResult)
            .join(LeadBrief, LeadBrief.research_run_id == ResearchRun.id)
            .outerjoin(QualificationResult, QualificationResult.research_run_id == ResearchRun.id)
            .where(
                ResearchRun.status == JobStatus.COMPLETED,
                ResearchRun.review_status == ReviewStatus.PENDING,
            )
            .order_by(ResearchRun.finished_at.desc())
            .limit(QUEUE_LIMIT)
        )
    ).all()
    items: list[QueueItem] = []
    for run, brief, qualification in rows:
        current = _current_brief(run, brief)
        if current is None:
            continue
        items.append(
            QueueItem(
                run=run,
                summary=current.sections.get("summary", {}),
                hard_reject=bool(qualification and qualification.hard_reject),
                recommended_rejection=qualification.rejection_reason if qualification else None,
                explanation=qualification.explanation if qualification else "",
                next_action=next_action_text(current),
                possible_duplicates=await duplicate_candidates(
                    db, run, current.sections.get("summary", {}).get("company")
                ),
            )
        )
    items.sort(
        key=lambda i: (
            not i.summary.get("qualifies"),
            i.hard_reject,
            -(i.summary.get("priority_score") or -1),
        )
    )
    return items


async def duplicate_candidates(
    db: AsyncSession,
    run: ResearchRun,
    company: str | None,
    identifiers: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Live accounts that may be this company: same domain (exact), same registry identifier
    (e.g. Companies House number), similar name (trigram), or flagged when the run started.
    Never merged silently; the reviewer decides."""
    found: dict[uuid.UUID, dict[str, Any]] = {}
    for scheme, value in identifiers or []:
        same_entity = (
            await db.execute(
                select(Account)
                .join(AccountIdentifier, AccountIdentifier.account_id == Account.id)
                .where(
                    AccountIdentifier.scheme == scheme,
                    AccountIdentifier.value == value,
                    Account.deleted_at.is_(None),
                )
            )
        ).scalars()
        for account in same_entity:
            found.setdefault(account.id, {"account": account, "match": f"identifier:{scheme}"})
    exact = (
        await db.execute(
            select(Account)
            .join(AccountDomain, AccountDomain.account_id == Account.id)
            .where(AccountDomain.domain == run.normalised_domain, Account.deleted_at.is_(None))
        )
    ).scalars()
    for account in exact:
        found[account.id] = {"account": account, "match": "domain"}
    if company:
        similar = (
            await db.execute(
                select(Account, func.similarity(Account.name, company))
                .where(
                    func.similarity(Account.name, company) >= NAME_SIMILARITY,
                    Account.deleted_at.is_(None),
                )
                .order_by(func.similarity(Account.name, company).desc())
                .limit(5)
            )
        ).all()
        for account, score in similar:
            found.setdefault(
                account.id, {"account": account, "match": "name", "similarity": round(score, 2)}
            )
    flagged = [uuid.UUID(a) for a in run.possible_duplicate_of if a]
    missing = [a for a in flagged if a not in found]
    if missing:
        for account in (
            await db.execute(
                select(Account).where(Account.id.in_(missing), Account.deleted_at.is_(None))
            )
        ).scalars():
            found[account.id] = {"account": account, "match": "flagged"}
    return list(found.values())


def describe_duplicates(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "account_id": str(f["account"].id),
            "name": f["account"].name,
            "primary_domain": f["account"].primary_domain,
            "match": f["match"],
            **({"similarity": f["similarity"]} if "similarity" in f else {}),
        }
        for f in found
    ]


# --- deciding --------------------------------------------------------------------------------


async def _locked_pending_run(db: AsyncSession, run_id: uuid.UUID) -> ResearchRun:
    run = (
        await db.execute(
            select(ResearchRun)
            .where(ResearchRun.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if run is None:
        raise NotFound("Research run not found.")
    if run.review_status != ReviewStatus.PENDING:
        raise Conflict(f"This prospect was already {run.review_status.value}.")
    return run


@dataclass
class ApproveInput:
    owner_id: uuid.UUID | None = None
    due_at: datetime | None = None
    task_title: str | None = None
    account_id: uuid.UUID | None = None
    create_new_account: bool = False
    override_reason: str | None = None


@dataclass
class Approval:
    account: Account
    created_account: bool
    lead: Lead
    opportunity: Opportunity | None
    contacts: list[Contact]
    task: Task


async def approve(
    db: AsyncSession, *, user: User, run_id: uuid.UUID, data: ApproveInput, settings: Settings
) -> Approval:
    run = await _locked_pending_run(db, run_id)
    if run.status != JobStatus.COMPLETED:
        raise Conflict(f"This run is {run.status.value}; only completed research can be approved.")
    brief = _current_brief(
        run,
        (
            await db.execute(select(LeadBrief).where(LeadBrief.research_run_id == run.id))
        ).scalar_one_or_none(),
    )
    snapshot = (
        await db.execute(
            select(ScoreSnapshot)
            .where(ScoreSnapshot.research_run_id == run.id)
            .order_by(ScoreSnapshot.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    qualification = (
        await db.execute(
            select(QualificationResult).where(QualificationResult.research_run_id == run.id)
        )
    ).scalar_one_or_none()
    if (
        brief is None
        or snapshot is None
        or snapshot.breakdown.get("attempt") != run.retry_count
        or qualification is None
    ):
        raise Conflict("This run has no current assessment and brief; retry the research first.")

    suppressed = await scoring.suppression_for(db, run.normalised_domain)
    if suppressed:
        raise Conflict(
            f"Suppressed ({suppressed}). Reject it with reason suppressed_account instead.",
            code="suppressed",
        )

    # A person may approve against the engines' advice, but must say why (audited).
    override = None
    if qualification.hard_reject or not snapshot.qualifies:
        reason = (data.override_reason or "").strip()
        if len(reason) < 10:
            why = (
                f"rejected by the ICP engine ({qualification.rejection_reason})"
                if qualification.hard_reject
                else "below the qualification threshold"
            )
            raise ValidationFailed(
                f"This prospect is {why}. To approve anyway, give an override reason "
                "(at least 10 characters).",
                code="override_required",
            )
        override = reason

    owner = await _owner(db, data.owner_id or user.id)
    facts = await scoring.load_facts(db, run)
    company = brief.sections.get("summary", {}).get("company")
    account, created = await _resolve_account(db, run, data, company, facts, owner, snapshot, user)
    await _record_identifiers(db, account, facts)
    now = _now()

    # Attach the research to the account. The append-only triggers allow exactly this:
    # account_id set once from NULL.
    for table in (Evidence, Observation, Claim, ScoreSnapshot):
        await db.execute(
            update(table)
            .where(table.research_run_id == run.id, table.account_id.is_(None))
            .values(account_id=account.id)
        )
    brief.account_id = account.id
    run.account_id = account.id
    run.review_status = ReviewStatus.APPROVED
    run.reviewed_by_id = user.id
    run.reviewed_at = now

    lead = Lead(
        account_id=account.id,
        research_run_id=run.id,
        source="url_research",
        owner_id=owner.id,
        status=LeadStatus.QUALIFIED,
        score_snapshot_id=snapshot.id,
        priority_score=snapshot.priority_score,
        priority_band=snapshot.priority_band,
        qualified_at=now,
    )
    db.add(lead)
    await db.flush()

    opportunity = await _opportunity(db, run, account, lead, owner, company)
    contacts = await _contacts(db, account, facts, run)

    title = (data.task_title or next_action_text(brief) or "Review the lead brief").strip()
    due = data.due_at or add_business_days(now, settings.task_due_business_days)
    task = Task(
        account_id=account.id,
        lead_id=lead.id,
        opportunity_id=opportunity.id if opportunity else None,
        title=title[:200],
        description=f"Next action from the lead brief for {run.normalised_domain}.",
        owner_id=owner.id,
        due_at=due,
        priority=TASK_PRIORITY.get(snapshot.priority_band, TaskPriority.NORMAL)
        if snapshot.priority_band
        else TaskPriority.NORMAL,
    )
    db.add(task)
    await db.flush()
    if opportunity:
        opportunity.next_action_task_id = task.id
    account.last_activity_at = now
    if account.next_activity_at is None or due < account.next_activity_at:
        account.next_activity_at = due

    _write_timeline(db, user, run, account, created, lead, opportunity, contacts, task, owner)
    audit.record(
        db,
        action="prospect.approved",
        object_table="research_runs",
        object_id=run.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value={"review_status": ReviewStatus.PENDING.value},
        new_value={
            "review_status": ReviewStatus.APPROVED.value,
            "account_id": str(account.id),
            "created_account": created,
            "lead_id": str(lead.id),
            "opportunity_id": str(opportunity.id) if opportunity else None,
            "task_id": str(task.id),
            "contacts": len(contacts),
            "owner_id": str(owner.id),
            "engine_qualified": snapshot.qualifies and not qualification.hard_reject,
        },
        reason=override,
    )
    if created:
        audit.record(
            db,
            action="account.created",
            object_table="accounts",
            object_id=account.id,
            user_id=user.id,
            source=AuditSource.API,
            new_value={"name": account.name, "primary_domain": account.primary_domain},
        )
    await db.flush()
    return Approval(account, created, lead, opportunity, contacts, task)


async def _owner(db: AsyncSession, owner_id: uuid.UUID) -> User:
    owner = await db.get(User, owner_id)
    if owner is None or not owner.is_active:
        raise ValidationFailed("The owner must be an active team member.", code="invalid_owner")
    return owner


async def _resolve_account(
    db: AsyncSession,
    run: ResearchRun,
    data: ApproveInput,
    company: str | None,
    facts: Facts,
    owner: User,
    snapshot: ScoreSnapshot,
    user: User,
) -> tuple[Account, bool]:
    found = await duplicate_candidates(db, run, company, registry_identifiers(facts))
    same_domain = [f["account"] for f in found if f["match"] == "domain"]
    same_entity = [f["account"] for f in found if str(f["match"]).startswith("identifier:")]
    account: Account | None = None
    if not same_domain and same_entity and not data.account_id:
        # The same registered company under another website (a rebrand or second domain):
        # it is the same legal entity, so the research joins that account with this domain.
        account = same_entity[0]
        db.add(AccountDomain(account_id=account.id, domain=run.normalised_domain))
    elif same_domain:
        # The domain already belongs to an account: the research can only attach to it.
        account = same_domain[0]
        if data.account_id and data.account_id != account.id:
            raise Conflict(
                f"{run.normalised_domain} already belongs to {account.name}; approve into that "
                "account instead.",
                code="domain_taken",
                details={"possible_duplicates": describe_duplicates(found)},
            )
    elif data.account_id:
        account = await db.get(Account, data.account_id)
        if (
            account is None
            or account.deleted_at is not None
            or not access.can_see(user, account.owner_id)
        ):
            raise ValidationFailed("That account does not exist.", code="invalid_account")
        db.add(AccountDomain(account_id=account.id, domain=run.normalised_domain))
    elif found and not data.create_new_account:
        raise Conflict(
            "This may be an existing account. Choose one (account_id) or confirm it is new "
            "(create_new_account).",
            code="possible_duplicate",
            details={"possible_duplicates": describe_duplicates(found)},
        )

    if account is not None:
        _copy_scores(account, snapshot)
        if account.account_type == AccountType.PROSPECT:
            account.account_type = AccountType.QUALIFIED_PROSPECT
        if account.owner_id is None:
            account.owner_id = owner.id
        return account, False

    address = _first_value(facts, "company.address")
    industry = _first_value(facts, "company.industry")
    country = str(address.get("addressCountry", "")).upper() if isinstance(address, dict) else ""
    city = address.get("addressLocality") if isinstance(address, dict) else None
    registered = _first_value(facts, "registry.companies_house")
    if not city and isinstance(registered, dict):
        city = registered.get("locality")
    filed = _first_value(facts, "registry.accounts")
    size_band = filed.get("size_band") if isinstance(filed, dict) else None
    description = _first_value(facts, "company.description")
    account = Account(
        name=(company or run.normalised_domain)[:300],
        primary_domain=run.normalised_domain,
        website_url=run.input_url,
        industry=str(industry["name"])[:120] if isinstance(industry, dict) else None,
        description=str(description) if isinstance(description, str) else None,
        hq_city=str(city)[:120] if city else None,
        hq_country=country if ISO2.match(country) else None,
        account_type=AccountType.QUALIFIED_PROSPECT,
        owner_id=owner.id,
        source="url_research",
        company_size_band=str(size_band)[:40] if size_band else None,
    )
    linkedin = _first_value(facts, "company.linkedin_company_url")
    if isinstance(linkedin, str):
        account.linkedin_company_url = linkedin
    _copy_scores(account, snapshot)
    db.add(account)
    await db.flush()
    db.add(AccountDomain(account_id=account.id, domain=run.normalised_domain, is_primary=True))
    return account, True


def registry_identifiers(facts: Facts) -> list[tuple[str, str]]:
    """(scheme, value) pairs from registry facts, for duplicate detection and the account."""
    out: list[tuple[str, str]] = []
    registered = facts.value("registry.companies_house")
    if registered and registered.get("number"):
        out.append(("companies_house", str(registered["number"])))
    wiki = facts.value("registry.wikidata")
    if wiki and wiki.get("qid"):
        out.append(("wikidata", str(wiki["qid"])))
    return out


async def _record_identifiers(db: AsyncSession, account: Account, facts: Facts) -> None:
    for scheme, value in registry_identifiers(facts):
        owner = (
            await db.execute(
                select(AccountIdentifier.account_id).where(
                    AccountIdentifier.scheme == scheme, AccountIdentifier.value == value
                )
            )
        ).scalar_one_or_none()
        if owner is None:
            db.add(AccountIdentifier(account_id=account.id, scheme=scheme, value=value))


def _first_value(facts: Facts, key: str) -> Any:
    found = sorted(facts.all(key), key=lambda f: -f.confidence)
    return found[0].value if found else None


def _copy_scores(account: Account, snapshot: ScoreSnapshot) -> None:
    for name in SCORE_FIELDS:
        setattr(account, name, getattr(snapshot, name))
    account.priority_score = snapshot.priority_score
    account.priority_band = snapshot.priority_band


async def _opportunity(
    db: AsyncSession,
    run: ResearchRun,
    account: Account,
    lead: Lead,
    owner: User,
    company: str | None,
) -> Opportunity | None:
    """The strongest detected problem becomes the Opportunity; no problem, no Opportunity."""
    top = (
        await db.execute(
            select(OpportunityCandidate, OpportunityCategory)
            .join(OpportunityCategory, OpportunityCategory.id == OpportunityCandidate.category_id)
            .where(OpportunityCandidate.research_run_id == run.id)
            .order_by(OpportunityCandidate.confidence.desc(), OpportunityCandidate.created_at)
            .limit(1)
        )
    ).first()
    if top is None:
        return None
    candidate, category = top
    service_id = (
        await db.execute(
            select(ServiceMatch.service_id).where(
                ServiceMatch.research_run_id == run.id, ServiceMatch.slot == ServiceSlot.PRIMARY
            )
        )
    ).scalar_one_or_none()
    opportunity = Opportunity(
        account_id=account.id,
        lead_id=lead.id,
        name=f"{category.name}: {company or run.normalised_domain}"[:200],
        problem=candidate.problem_statement,
        category_id=category.id,
        service_id=service_id,
        owner_id=owner.id,
    )
    db.add(opportunity)
    await db.flush()
    return opportunity


async def _contacts(
    db: AsyncSession, account: Account, facts: Facts, run: ResearchRun
) -> list[Contact]:
    """People named on the company's own pages and current registered officers. No email or
    phone is invented: those stay empty unless the page published them next to the person."""
    existing = [
        name
        for name in (
            await db.execute(
                select(Contact.name).where(
                    Contact.account_id == account.id, Contact.deleted_at.is_(None)
                )
            )
        ).scalars()
    ]
    collected = {
        str(e.id): e.collected_at
        for e in (
            await db.execute(select(Evidence).where(Evidence.research_run_id == run.id))
        ).scalars()
    }
    added: list[Contact] = []
    for fact in sorted(named_people(facts), key=lambda f: -f.confidence):
        name = str(fact.value.get("name", "")).strip()
        if not name or any(same_person(name, known) for known in existing):
            continue
        existing.append(name)
        title = fact.value.get("title")
        registry = fact.value.get("source") == "companies_house"
        contact = Contact(
            account_id=account.id,
            name=name[:200],
            title=str(title)[:200] if title else None,
            source="companies_house" if registry else "company_website",
            source_url=fact.source_url,
            collected_at=collected.get(fact.evidence_id, _now()),
            confidence=Decimal(str(round(fact.confidence, 2))),
            decision_maker_role=role_for(str(title) if title else None),
        )
        db.add(contact)
        added.append(contact)
    await db.flush()
    return added


def _write_timeline(
    db: AsyncSession,
    user: User,
    run: ResearchRun,
    account: Account,
    created: bool,
    lead: Lead,
    opportunity: Opportunity | None,
    contacts: list[Contact],
    task: Task,
    owner: User,
) -> None:
    def add(event_type: str, summary: str, table: str, ref: uuid.UUID, **kw: Any) -> None:
        timeline.add(
            db,
            account_id=account.id,
            event_type=event_type,
            summary=summary,
            actor_id=kw.get("actor", user.id),
            ref_table=table,
            ref_id=ref,
            occurred_at=kw.get("at"),
        )

    if created:
        add(
            "account.created",
            f"Account created from research on {run.normalised_domain}.",
            "accounts",
            account.id,
            at=run.created_at,
        )
    add(
        "research.completed",
        f"Website {run.normalised_domain} researched and analysed.",
        "research_runs",
        run.id,
        actor=run.requested_by_id,
        at=run.finished_at,
    )
    add("lead.qualified", f"Lead approved and qualified; owner {owner.name}.", "leads", lead.id)
    if opportunity:
        add(
            "opportunity.created",
            f"Opportunity: {opportunity.name}.",
            "opportunities",
            opportunity.id,
        )
    for contact in contacts:
        add(
            "contact.added",
            f"Contact {contact.name}{f', {contact.title}' if contact.title else ''} "
            "(from the company website).",
            "contacts",
            contact.id,
        )
    due = task.due_at.date().isoformat() if task.due_at else "no date"
    add("task.created", f"Task for {owner.name}, due {due}: {task.title}", "tasks", task.id)


async def reject(
    db: AsyncSession,
    *,
    user: User,
    run_id: uuid.UUID,
    reason: RejectionReason,
    note: str | None,
    suppress: bool,
) -> ResearchRun:
    run = await _locked_pending_run(db, run_id)
    if run.status not in (JobStatus.COMPLETED, JobStatus.FAILED):
        raise Conflict(f"This run is {run.status.value}; wait for it to finish or cancel it.")
    run.review_status = ReviewStatus.REJECTED
    run.rejection_reason = reason
    run.rejection_note = (note or "").strip() or None
    run.reviewed_by_id = user.id
    run.reviewed_at = _now()
    if suppress:
        exists = (
            await db.execute(
                select(Suppression).where(
                    Suppression.kind == SuppressionKind.DOMAIN,
                    Suppression.value == run.normalised_domain,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                Suppression(
                    kind=SuppressionKind.DOMAIN,
                    value=run.normalised_domain,
                    reason=f"Rejected: {reason.value}"
                    + (f" ({run.rejection_note})" if run.rejection_note else ""),
                    added_by_id=user.id,
                )
            )
    owners = (
        await db.execute(
            select(AccountDomain.account_id).where(AccountDomain.domain == run.normalised_domain)
        )
    ).scalars()
    for account_id in owners:  # research on an existing account stays on its timeline
        timeline.add(
            db,
            account_id=account_id,
            event_type="research.rejected",
            summary=f"Research on {run.normalised_domain} rejected: {reason.value}.",
            actor_id=user.id,
            ref_table="research_runs",
            ref_id=run.id,
        )
    audit.record(
        db,
        action="prospect.rejected",
        object_table="research_runs",
        object_id=run.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value={"review_status": ReviewStatus.PENDING.value},
        new_value={
            "review_status": ReviewStatus.REJECTED.value,
            "rejection_reason": reason.value,
            "suppressed": suppress,
        },
        reason=run.rejection_note,
    )
    return run
