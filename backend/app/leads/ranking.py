"""Ranks accounts and explains each rank from stored data only (master context §15, slice 2.6).

The order is the priority score: the weighted blend of the ten dimensions from the active scoring
config (SCORING_SPEC.md), which already covers ICP, negative ICP, opportunity, intent, timing,
service fit, similarity, data confidence and commercial potential. Ties go to better timing,
then more trustworthy data, then the account touched least recently. The explanation reads the
latest score snapshot's breakdown, dated buying signals with their source, and open
opportunities. Nothing is invented: a dimension without evidence is reported as Unknown.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, and_, cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account, Suppression
from app.auth.models import User
from app.catalogue.models import Service
from app.core.enums import AccountType, ObservationArea, PriorityBand, SuppressionKind
from app.core.search import contains_pattern
from app.crm.models import Opportunity
from app.evidence.models import Evidence, Observation
from app.leads.interpret import Filters, Vocabulary
from app.opportunities.models import OpportunityCategory
from app.research.models import ResearchRun
from app.scoring.models import ScoreSnapshot

DIMENSION_LABELS = {
    "icp_score": "ICP fit",
    "opportunity_score": "Opportunity",
    "intent_score": "Intent",
    "buyer_confidence": "Buyer confidence",
    "data_confidence": "Data confidence",
    "service_fit": "Service fit",
    "timing_score": "Timing",
    "commercial_potential": "Commercial potential",
    "client_similarity": "Client similarity",
    "evidence_strength": "Evidence strength",
}
SIGNAL_LABELS = {
    "developer_hiring": "Hiring developers",
    "cto_hiring": "Hiring a CTO",
    "product_hiring": "Hiring for product",
    "hiring": "Hiring",
    "funding": "Raised funding",
    "financing": "Secured lending",
    "product_launch": "Product launch",
    "new_leader": "New leadership",
    "acquisition": "Acquisition",
    "expansion": "Expanding",
    "new_service": "New service",
    "rebrand": "Rebrand",
}
OPEN_PROSPECTS = (AccountType.PROSPECT, AccountType.QUALIFIED_PROSPECT)


@dataclass
class Reason:
    kind: str  # score | gate | unknown | signal | opportunity
    text: str
    source_url: str | None = None


@dataclass
class Ranked:
    account: Account
    reasons: list[Reason] = field(default_factory=list)
    scored_at: datetime | None = None


async def vocabulary(db: AsyncSession) -> Vocabulary:
    """Industries and cities already on accounts, so the interpreter knows the CRM's words."""
    live = Account.deleted_at.is_(None)
    industries = (
        await db.execute(
            select(Account.industry).where(live, Account.industry.is_not(None)).distinct()
        )
    ).scalars()
    cities = (
        await db.execute(
            select(Account.hq_city).where(live, Account.hq_city.is_not(None)).distinct()
        )
    ).scalars()
    categories = (await db.execute(select(OpportunityCategory.key, OpportunityCategory.name))).all()
    return Vocabulary(
        industries=[i for i in industries if i],
        cities=[c for c in cities if c],
        category_names={key: name for key, name in categories},
    )


def _signal_exists(kinds: list[str], since: datetime) -> Any:
    return exists(
        select(Observation.id)
        .join(ResearchRun, ResearchRun.id == Observation.research_run_id)
        .join(Evidence, Evidence.id == Observation.evidence_id)
        .where(
            ResearchRun.account_id == Account.id,
            Observation.area == ObservationArea.SIGNALS,
            cast(Observation.value["signal"].astext, TEXT).in_(kinds),
            func.coalesce(Evidence.published_at, Evidence.collected_at) >= since,
        )
    )


def candidates(user: User, f: Filters) -> Select[Any]:
    stmt = select(Account).where(Account.deleted_at.is_(None))
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)

    types = list(f.account_types) or (list(OPEN_PROSPECTS) if f.top_leads else [])
    if types:
        stmt = stmt.where(Account.account_type.in_(types))
    if AccountType.SUPPRESSED not in types:
        # Never suggest a company on the do-not-contact list (§12B).
        stmt = stmt.where(
            Account.account_type != AccountType.SUPPRESSED,
            ~exists(
                select(Suppression.id).where(
                    or_(
                        and_(
                            Suppression.kind == SuppressionKind.DOMAIN,
                            Suppression.value == Account.primary_domain,
                        ),
                        and_(
                            Suppression.kind == SuppressionKind.ACCOUNT,
                            Suppression.value == cast(Account.id, TEXT),
                        ),
                    )
                )
            ),
        )
    if f.top_leads:
        stmt = stmt.where(
            Account.priority_score.is_not(None), Account.priority_band != PriorityBand.REJECT
        )

    text_terms = [Account.industry.ilike(contains_pattern(i)) for i in f.industries]
    for topic in f.topics:
        pattern = contains_pattern(topic)
        text_terms += [
            Account.name.ilike(pattern),
            Account.industry.ilike(pattern),
            Account.description.ilike(pattern),
        ]
    if text_terms:
        stmt = stmt.where(or_(*text_terms))
    if f.cities:
        stmt = stmt.where(or_(*(Account.hq_city.ilike(c) for c in f.cities)))
    if f.country:
        stmt = stmt.where(Account.hq_country == f.country)
    if f.categories:
        stmt = stmt.where(
            exists(
                select(Opportunity.id)
                .join(OpportunityCategory, OpportunityCategory.id == Opportunity.category_id)
                .where(
                    Opportunity.account_id == Account.id,
                    Opportunity.deleted_at.is_(None),
                    OpportunityCategory.key.in_(f.categories),
                )
            )
        )
    since = datetime.now(UTC) - f.signal_window
    for group in f.signal_groups:
        stmt = stmt.where(_signal_exists(group, since))
    if f.bands:
        stmt = stmt.where(Account.priority_band.in_(f.bands))
    if f.owner == "me":
        stmt = stmt.where(Account.owner_id == user.id)
    elif f.owner == "unassigned":
        stmt = stmt.where(Account.owner_id.is_(None))

    return stmt.order_by(
        Account.priority_score.desc().nulls_last(),
        Account.timing_score.desc().nulls_last(),
        Account.data_confidence.desc().nulls_last(),
        Account.last_activity_at.asc().nulls_first(),
        Account.name,
        Account.id,
    ).limit(f.limit)


def _score_reasons(breakdown: dict[str, Any]) -> list[Reason]:
    dims: dict[str, dict[str, Any]] = breakdown.get("dimensions") or {}
    known = [(name, d) for name, d in dims.items() if d.get("contribution") is not None]
    known.sort(key=lambda item: item[1]["contribution"], reverse=True)
    reasons = [
        Reason(
            "score",
            f"{DIMENSION_LABELS.get(name, name)} {round(d['score'])}"
            f" ({round(float(d['weight']) * 100)}% of the priority score)",
        )
        for name, d in known[:3]
    ]
    for gate in breakdown.get("gates") or []:
        if gate.get("applied"):
            reasons.append(Reason("gate", f"Capped at {gate['cap']}: {gate['why']}"))
    unknown = [DIMENSION_LABELS.get(n, n) for n in breakdown.get("unknown") or []]
    if unknown:
        reasons.append(Reason("unknown", "Unknown, not counted: " + ", ".join(unknown)))
    return reasons


async def explain(db: AsyncSession, accounts: list[Account], since: datetime) -> list[Ranked]:
    ids = [a.id for a in accounts]
    if not ids:
        return []

    latest: dict[uuid.UUID, ScoreSnapshot] = {}
    for snap in (
        await db.execute(
            select(ScoreSnapshot)
            .where(ScoreSnapshot.account_id.in_(ids))
            .order_by(ScoreSnapshot.created_at.desc())
        )
    ).scalars():
        latest.setdefault(snap.account_id, snap)  # type: ignore[arg-type]

    signals: dict[uuid.UUID, list[Reason]] = {}
    rows = await db.execute(
        select(
            ResearchRun.account_id,
            Observation.value,
            Evidence.source_url,
            Evidence.published_at,
            Evidence.collected_at,
        )
        .join(Observation, Observation.research_run_id == ResearchRun.id)
        .join(Evidence, Evidence.id == Observation.evidence_id)
        .where(
            ResearchRun.account_id.in_(ids),
            Observation.area == ObservationArea.SIGNALS,
            func.coalesce(Evidence.published_at, Evidence.collected_at) >= since,
        )
        .order_by(func.coalesce(Evidence.published_at, Evidence.collected_at).desc())
    )
    for account_id, value, url, published, collected in rows.all():
        found = signals.setdefault(account_id, [])
        if len(found) >= 2:
            continue
        kind = (value or {}).get("signal", "")
        title = (value or {}).get("title")
        when = (published or collected).date().isoformat()
        text = SIGNAL_LABELS.get(kind, kind.replace("_", " ").capitalize() or "Signal")
        found.append(
            Reason("signal", f"{text}: {title} ({when})" if title else f"{text} ({when})", url)
        )

    opportunities: dict[uuid.UUID, list[Reason]] = {}
    for account_id, name, service in (
        await db.execute(
            select(Opportunity.account_id, Opportunity.name, Service.name)
            .outerjoin(Service, Service.id == Opportunity.service_id)
            .where(Opportunity.account_id.in_(ids), Opportunity.deleted_at.is_(None))
            .order_by(Opportunity.created_at.desc())
        )
    ).all():
        found = opportunities.setdefault(account_id, [])
        if len(found) < 2:
            found.append(Reason("opportunity", f"{name}" + (f" → {service}" if service else "")))

    ranked = []
    for account in accounts:
        found_snap = latest.get(account.id)
        item = Ranked(account, scored_at=found_snap.created_at if found_snap else None)
        item.reasons = [
            *(
                _score_reasons(found_snap.breakdown)
                if found_snap
                else [Reason("unknown", "Not scored yet")]
            ),
            *signals.get(account.id, []),
            *opportunities.get(account.id, []),
        ]
        ranked.append(item)
    return ranked


async def rank(db: AsyncSession, *, user: User, filters: Filters) -> list[Ranked]:
    accounts = list((await db.execute(candidates(user, filters))).scalars())
    return await explain(db, accounts, datetime.now(UTC) - filters.signal_window)
