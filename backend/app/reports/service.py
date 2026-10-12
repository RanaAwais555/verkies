"""Dashboards and the conversion funnel (master context §13, slice 3.3).

Every figure is computed on request from the records themselves, over the accounts the user may
see, and carries `definition`: the rule that produced it, in words a salesperson can check. Where
a page can list the records behind a figure, `href` points there. Nothing is estimated: a figure
with nothing to measure is None (shown as Unknown) and money with no value entered is counted
apart, never as zero.
"""

import statistics
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account
from app.auth.models import User
from app.catalogue.models import Service
from app.clients import health, referrals
from app.config import Settings
from app.core.enums import (
    ActivityDirection,
    HealthColour,
    ObservationArea,
    ReviewStatus,
    StageOutcome,
    TaskStatus,
)
from app.crm import service as crm
from app.crm.follow_ups import follow_up_flags
from app.crm.models import Activity, Lead, Opportunity, Task
from app.deals.models import Deal, DealStageChange, Pipeline, PipelineStage
from app.deals.service import LOST_REASON_LABELS, weighted
from app.evidence.models import Evidence, Observation
from app.leads.interpret import COUNTRIES
from app.leads.ranking import SIGNAL_LABELS
from app.opportunities.models import OpportunityCategory
from app.research.models import ResearchRun

Period = Literal["7d", "30d", "90d", "365d", "ytd"]
PERIOD_LABELS: dict[str, str] = {
    "7d": "the last 7 days",
    "30d": "the last 30 days",
    "90d": "the last 90 days",
    "365d": "the last 12 months",
    "ytd": "the year to date",
}
Unit = Literal["count", "percent", "days", "money", "score"]
LIKELY_CLOSE_DAYS = 30
# Pipeline stages at or past a proposal, for the funnel's Proposal step.
PROPOSAL_OR_LATER = ("proposal", "negotiation", "verbal_agreement", "won")
TOP = 8
DASH = chr(0x2013)  # an en dash for ranges, written so no ambiguous character is in the source
ICP_HIGH, ICP_MID, ICP_LOW = f"ICP 70{DASH}100", f"ICP 40{DASH}69", f"ICP 0{DASH}39"


def _now() -> datetime:
    return datetime.now(UTC)


def window(period: Period, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or _now()
    if period == "ytd":
        return datetime(now.year, 1, 1, tzinfo=UTC), now
    return now - timedelta(days=int(period.removesuffix("d"))), now


# --- shapes ------------------------------------------------------------------------------------


@dataclass
class Money:
    amount: float
    currency: str


@dataclass
class Figure:
    key: str
    label: str
    value: float | None  # None is Unknown
    unit: Unit
    definition: str
    currency: str | None = None
    detail: str | None = None
    href: str | None = None


Cell = int | float | str | None | list[Money]


@dataclass
class Row:
    label: str
    values: list[Cell]
    href: str | None = None


@dataclass
class Table:
    key: str
    label: str
    definition: str
    columns: list[str]
    rows: list[Row]
    note: str | None = None


@dataclass
class FunnelStep:
    key: str
    label: str
    count: int
    definition: str


@dataclass
class Dashboard:
    period: Period
    start: datetime
    end: datetime
    figures: list[Figure] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    funnel: list[FunnelStep] | None = None


# --- helpers -----------------------------------------------------------------------------------


def _scoped(stmt: Any, user: User) -> Any:
    """Limit a query already joined to Account to live accounts the user may see."""
    stmt = stmt.where(Account.deleted_at.is_(None))
    clause = access.visible(user)
    return stmt if clause is None else stmt.where(clause)


def _between(column: Any, start: datetime, end: datetime) -> Any:
    return (column >= start) & (column < end)


def _pct(part: int, whole: int) -> float | None:
    return None if whole == 0 else round(100 * part / whole, 1)


def _of(part: int, whole: int) -> str:
    return f"{part} of {whole}"


def _money_by_currency(rows: Iterable[tuple[Decimal | None, str]]) -> tuple[list[Money], int]:
    """Known amounts summed per currency, and how many had no amount."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    unknown = 0
    for amount, currency in rows:
        if amount is None:
            unknown += 1
        else:
            totals[currency] += amount
    return [Money(float(v), c) for c, v in sorted(totals.items())], unknown


def _money_figures(
    key: str, label: str, definition: str, rows: list[tuple[Decimal | None, str]], href: str | None
) -> list[Figure]:
    totals, unknown = _money_by_currency(rows)
    note = f"{len(rows)} {'deal' if len(rows) == 1 else 'deals'}"
    if unknown:
        note += f"; {unknown} without a value, not counted"
    if not totals:
        # Nothing to add up: zero when there were no deals, Unknown when none had a value.
        value = 0.0 if not rows else None
        return [Figure(key, label, value, "money", definition, "GBP", note, href)]
    return [
        Figure(
            key if i == 0 else f"{key}_{m.currency.lower()}",
            label if len(totals) == 1 else f"{label} ({m.currency})",
            float(m.amount),
            "money",
            definition,
            m.currency,
            note,
            href,
        )
        for i, m in enumerate(totals)
    ]


def _deal_rows(
    found: Iterable[tuple[Deal, PipelineStage]],
) -> tuple[list[tuple[Decimal | None, str]], list[tuple[Decimal | None, str]]]:
    values, weights = [], []
    for deal, stage in found:
        values.append((deal.value, deal.currency))
        weights.append((weighted(deal, stage) if deal.value is not None else None, deal.currency))
    return values, weights


async def _deals(
    db: AsyncSession, user: User, *conditions: Any, mine: bool = False
) -> list[tuple[Deal, Account, PipelineStage, Pipeline]]:
    stmt = (
        select(Deal, Account, PipelineStage, Pipeline)
        .join(Account, Account.id == Deal.account_id)
        .join(PipelineStage, PipelineStage.id == Deal.stage_id)
        .join(Pipeline, Pipeline.id == Deal.pipeline_id)
        .where(Deal.deleted_at.is_(None), *conditions)
    )
    stmt = _scoped(stmt, user)
    if mine:
        stmt = stmt.where(crm.responsible(Deal.owner_id) == user.id)
    return [tuple(r) for r in (await db.execute(stmt)).all()]


async def _count(db: AsyncSession, stmt: Select[Any]) -> int:
    return int((await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())


def _closed_in(start: datetime, end: datetime, outcome: StageOutcome) -> list[Any]:
    return [Deal.outcome == outcome, _between(Deal.closed_at, start, end)]


# --- funnel ------------------------------------------------------------------------------------

FUNNEL: list[tuple[str, str, str]] = [
    ("discovered", "Discovery", "Companies first researched in the period (one per website)."),
    ("qualified", "Qualified", "Approved into the CRM: the company has a qualified lead."),
    ("contacted", "Contacted", "Any call, meeting or message logged with the company."),
    ("reply", "Reply", "They replied: an inbound message, a connected call or a meeting."),
    ("meeting", "Meeting", "A meeting with the company was logged."),
    ("opportunity", "Opportunity", "A deal was opened for the company."),
    ("proposal", "Proposal", "A deal reached the Proposal stage or beyond."),
    ("won", "Won", "A deal was won."),
]


async def funnel(
    db: AsyncSession, *, user: User, start: datetime, end: datetime
) -> list[FunnelStep]:
    """§13's conversion funnel for the companies first researched in the period.

    A company counts at a step when it reached that step or any later one, so each step is a
    subset of the one before and the conversion between steps is meaningful.
    """
    first_seen = (
        select(ResearchRun.normalised_domain, func.min(ResearchRun.created_at).label("first"))
        .group_by(ResearchRun.normalised_domain)
        .subquery()
    )
    runs = (
        await db.execute(
            select(
                ResearchRun.normalised_domain, ResearchRun.account_id, ResearchRun.requested_by_id
            )
            .join(first_seen, first_seen.c.normalised_domain == ResearchRun.normalised_domain)
            .where(_between(first_seen.c.first, start, end))
        )
    ).all()
    accounts: dict[str, set[uuid.UUID]] = defaultdict(set)
    requested: dict[str, set[uuid.UUID | None]] = defaultdict(set)
    for domain, account_id, requested_by in runs:
        accounts.setdefault(domain, set())
        requested[domain].add(requested_by)
        if account_id is not None:
            accounts[domain].add(account_id)

    # What the user may see: accounts they can read; a never-approved company only when the user
    # sees every account or asked for that research themselves.
    all_ids = {a for ids in accounts.values() for a in ids}
    visible_ids: set[uuid.UUID] = set()
    if all_ids:
        visible_ids = set(
            (
                await db.execute(_scoped(select(Account.id).where(Account.id.in_(all_ids)), user))
            ).scalars()
        )
    sees_all = access.visible(user) is None
    cohort = {
        d: ids & visible_ids
        for d, ids in accounts.items()
        if (ids & visible_ids) or (not ids and (sees_all or user.id in requested[d]))
    }
    ids = {a for found in cohort.values() for a in found}

    async def having(stmt: Select[Any]) -> set[uuid.UUID]:
        return set((await db.execute(stmt)).scalars()) if ids else set()

    qualified = await having(
        select(Lead.account_id).where(Lead.account_id.in_(ids), Lead.qualified_at.is_not(None))
    )
    contacted = await having(
        select(Activity.account_id).where(
            Activity.account_id.in_(ids), Activity.direction != ActivityDirection.INTERNAL
        )
    )
    replied = await having(
        select(Activity.account_id).where(
            Activity.account_id.in_(ids),
            Activity.direction.in_((ActivityDirection.INBOUND, ActivityDirection.CONVERSATION)),
        )
    )
    met = await having(
        select(Activity.account_id).where(
            Activity.account_id.in_(ids), Activity.activity_type == "meeting"
        )
    )
    with_deal = await having(
        select(Deal.account_id).where(Deal.account_id.in_(ids), Deal.deleted_at.is_(None))
    )
    proposal = await having(
        select(Deal.account_id)
        .join(DealStageChange, DealStageChange.deal_id == Deal.id)
        .join(PipelineStage, PipelineStage.id == DealStageChange.to_stage_id)
        .where(
            Deal.account_id.in_(ids),
            Deal.deleted_at.is_(None),
            PipelineStage.key.in_(PROPOSAL_OR_LATER),
        )
    )
    won = await having(
        select(Deal.account_id).where(
            Deal.account_id.in_(ids), Deal.deleted_at.is_(None), Deal.outcome == StageOutcome.WON
        )
    )
    reached = [qualified, contacted, replied, met, with_deal, proposal, won]

    furthest: list[int] = []
    for found in cohort.values():
        step = 0
        for i, members in enumerate(reached, start=1):
            if found & members:
                step = i
        furthest.append(step)
    return [
        FunnelStep(key, label, sum(1 for f in furthest if f >= i), definition)
        for i, (key, label, definition) in enumerate(FUNNEL)
    ]


# --- sales -------------------------------------------------------------------------------------


async def sales(
    db: AsyncSession, *, user: User, settings: Settings, period: Period, mine: bool
) -> Dashboard:
    start, end = window(period)
    when = PERIOD_LABELS[period]
    board = Dashboard(period, start, end)
    figures = board.figures

    def owned(stmt: Select[Any], column: Any) -> Select[Any]:
        stmt = _scoped(stmt, user)
        return stmt.where(crm.responsible(column) == user.id) if mine else stmt

    base_leads = select(Lead.id).join(Account, Account.id == Lead.account_id)
    base_leads = owned(base_leads.where(Lead.deleted_at.is_(None)), Lead.owner_id)
    new_leads = await _count(db, base_leads.where(_between(Lead.created_at, start, end)))
    qualified = await _count(db, base_leads.where(_between(Lead.qualified_at, start, end)))
    opportunities = await _count(
        db,
        owned(
            select(Opportunity.id)
            .join(Account, Account.id == Opportunity.account_id)
            .where(Opportunity.deleted_at.is_(None), _between(Opportunity.created_at, start, end)),
            Opportunity.owner_id,
        ),
    )
    figures += [
        Figure("new_leads", "New leads", new_leads, "count", f"Leads created in {when}."),
        Figure(
            "qualified_leads",
            "Qualified leads",
            qualified,
            "count",
            f"Leads approved and qualified in {when}.",
        ),
        Figure(
            "new_opportunities",
            "New opportunities",
            opportunities,
            "count",
            f"Opportunities created in {when}, on approval or later.",
        ),
    ]

    opened = await _deals(db, user, _between(Deal.created_at, start, end), mine=mine)
    figures.append(
        Figure(
            "deals_opened",
            "Deals opened",
            len(opened),
            "count",
            f"Deals opened in {when}, in any pipeline.",
            href="/pipeline",
        )
    )

    open_deals = await _deals(db, user, Deal.outcome == StageOutcome.OPEN, mine=mine)
    values, weights = _deal_rows((d, s) for d, _, s, _ in open_deals)
    figures += _money_figures(
        "pipeline",
        "Open pipeline",
        "The value of every open deal today, as entered by a person.",
        values,
        "/pipeline",
    )
    figures += _money_figures(
        "weighted_pipeline",
        "Weighted pipeline",
        "Each open deal's value times its probability (the deal's own, or its stage's). "
        "Deals without a value or a probability are left out.",
        [w for w in weights if w[0] is not None],
        "/pipeline",
    )

    won = await _deals(db, user, *_closed_in(start, end, StageOutcome.WON), mine=mine)
    lost = await _deals(db, user, *_closed_in(start, end, StageOutcome.LOST), mine=mine)
    figures += _money_figures(
        "won_value",
        "Won",
        f"The value of deals won in {when}.",
        [(d.value, d.currency) for d, *_ in won],
        "/pipeline",
    )
    figures += _money_figures(
        "lost_value",
        "Lost",
        f"The value of deals lost in {when}.",
        [(d.value, d.currency) for d, *_ in lost],
        "/pipeline",
    )
    figures.append(
        Figure(
            "win_rate",
            "Win rate",
            _pct(len(won), len(won) + len(lost)),
            "percent",
            f"Deals won out of deals won or lost in {when}. Unknown until a deal closes.",
            detail=_of(len(won), len(won) + len(lost)) + " closed deals",
        )
    )
    cycles = [(d.closed_at - d.created_at).days for d, *_ in won if d.closed_at]
    figures.append(
        Figure(
            "sales_cycle",
            "Sales cycle",
            float(statistics.median(cycles)) if cycles else None,
            "days",
            f"Median days from opening a deal to winning it, for deals won in {when}.",
            detail=f"{len(cycles)} won {'deal' if len(cycles) == 1 else 'deals'}",
        )
    )

    overdue = await _count(
        db,
        owned(
            select(Task.id)
            .join(Account, Account.id == Task.account_id)
            .where(
                Task.deleted_at.is_(None),
                Task.status.in_((TaskStatus.OPEN, TaskStatus.IN_PROGRESS)),
                Task.due_at < _now(),
            ),
            Task.owner_id,
        ),
    )
    figures.append(
        Figure(
            "overdue_tasks",
            "Overdue tasks",
            overdue,
            "count",
            "Open tasks whose due date has passed, today.",
            href="/tasks?due=overdue",
        )
    )

    flags: Counter[str] = Counter(
        f.kind for f in await follow_up_flags(db, user=user, settings=settings, mine=mine)
    )
    board.tables.append(
        Table(
            "follow_ups",
            "Follow-ups",
            "The follow-up engine's flags today: overdue follow-ups, opportunities without an "
            "owned and dated next action, opportunities quiet for "
            f"{settings.stale_opportunity_days} days and deals quiet for "
            f"{settings.inactive_deal_days} days.",
            ["Now"],
            [
                Row(label, [flags[kind]], f"/follow-ups?kind={kind}")
                for kind, label in (
                    ("overdue_follow_up", "Overdue follow-ups"),
                    ("no_next_action", "No next action"),
                    ("stale_opportunity", "Stale opportunities"),
                    ("inactive_deal", "Inactive deals"),
                )
            ],
        )
    )

    activity_stmt = _scoped(
        select(Activity.activity_type, Activity.direction)
        .join(Account, Account.id == Activity.account_id)
        .where(_between(Activity.occurred_at, start, end)),
        user,
    )
    if mine:
        activity_stmt = activity_stmt.where(Activity.actor_id == user.id)
    kinds: Counter[str] = Counter()
    replies = 0
    for kind, direction in (await db.execute(activity_stmt)).all():
        kinds[kind] += 1
        replies += direction in (ActivityDirection.INBOUND, ActivityDirection.CONVERSATION)
    board.tables.append(
        Table(
            "activity",
            "Activity logged",
            f"Calls, meetings, messages and notes logged as happening in {when}.",
            ["Logged"],
            [
                Row(label, [kinds[kind]])
                for kind, label in (
                    ("call", "Calls"),
                    ("meeting", "Meetings"),
                    ("message", "Messages"),
                    ("note", "Notes"),
                )
            ],
            note=f"{replies} of these were replies or conversations."
            if sum(kinds.values())
            else None,
        )
    )
    board.funnel = await funnel(db, user=user, start=start, end=end)
    return board


# --- lead intelligence -------------------------------------------------------------------------


COUNTRY_NAMES = {code: name for code, name in COUNTRIES.values()}
ACRONYMS = {"csv": "CSV", "ai": "AI", "seo": "SEO", "crm": "CRM", "api": "API"}


def _words(key: str) -> str:
    """'csv_import' as 'CSV import': a stored key as a person would write it."""
    words = [ACRONYMS.get(w, w) for w in key.replace("-", "_").split("_") if w]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def _bucket(score: Decimal) -> str:
    low = min(int(score) // 10 * 10, 90)
    return f"{low}{DASH}{low + 9 if low < 90 else 100}"


def _icp_band(score: Decimal | None) -> str:
    if score is None:
        return "Unknown ICP"
    if score >= 70:
        return ICP_HIGH
    if score >= 40:
        return ICP_MID
    return ICP_LOW


async def lead_intelligence(db: AsyncSession, *, user: User, period: Period) -> Dashboard:
    start, end = window(period)
    when = PERIOD_LABELS[period]
    board = Dashboard(period, start, end)

    researched = await _count(
        db,
        select(ResearchRun.normalised_domain)
        .where(_between(ResearchRun.created_at, start, end))
        .distinct(),
    )
    reviews = (
        await db.execute(
            select(ResearchRun.review_status, ResearchRun.rejection_reason).where(
                _between(ResearchRun.reviewed_at, start, end),
                ResearchRun.review_status.in_((ReviewStatus.APPROVED, ReviewStatus.REJECTED)),
            )
        )
    ).all()
    approved = sum(1 for s, _ in reviews if s is ReviewStatus.APPROVED)
    rejected = len(reviews) - approved
    board.figures += [
        Figure(
            "researched",
            "Companies researched",
            researched,
            "count",
            f"Websites researched in {when}, each counted once.",
            href="/research",
        ),
        Figure(
            "qualification_rate",
            "Qualification rate",
            _pct(approved, len(reviews)),
            "percent",
            f"Prospects approved out of all decided in {when}.",
            detail=_of(approved, len(reviews)) + " decided",
        ),
        Figure(
            "rejection_rate",
            "Rejection rate",
            _pct(rejected, len(reviews)),
            "percent",
            f"Prospects rejected out of all decided in {when}.",
            detail=_of(rejected, len(reviews)) + " decided",
        ),
    ]
    reasons = Counter(
        r.value if r else "no_reason" for s, r in reviews if s is ReviewStatus.REJECTED
    )
    board.tables.append(
        Table(
            "rejection_reasons",
            "Why prospects were rejected",
            f"The reason chosen for each prospect rejected in {when}.",
            ["Rejected"],
            [Row(_words(k), [n]) for k, n in reasons.most_common()],
        )
    )

    leads = (
        await db.execute(
            _scoped(
                select(Lead, Account)
                .join(Account, Account.id == Lead.account_id)
                .where(Lead.deleted_at.is_(None), _between(Lead.qualified_at, start, end)),
                user,
            )
        )
    ).all()
    scores = [lead.priority_score for lead, _ in leads if lead.priority_score is not None]
    board.figures.append(
        Figure(
            "lead_quality",
            "Lead quality",
            round(float(sum(scores) / len(scores)), 1) if scores else None,
            "score",
            f"Average priority score of leads qualified in {when}. Unscored leads are left out.",
            detail=f"{len(scores)} scored of {len(leads)} qualified",
        )
    )
    confidences = [a.data_confidence for _, a in leads if a.data_confidence is not None]
    board.figures.append(
        Figure(
            "data_confidence",
            "Data confidence",
            round(float(sum(confidences) / len(confidences)), 1) if confidences else None,
            "score",
            f"Average data confidence of the companies whose leads were qualified in {when}.",
            detail=f"{len(confidences)} of {len(leads)} known",
        )
    )

    bands = Counter(lead.priority_band.value if lead.priority_band else None for lead, _ in leads)
    board.tables.append(
        Table(
            "priority_bands",
            "Leads by priority band",
            f"Leads qualified in {when}, by the priority band they were qualified with.",
            ["Leads"],
            [
                Row(label, [bands[key]])
                for key, label in (
                    ("hot", "Hot"),
                    ("high", "High"),
                    ("qualified", "Qualified"),
                    ("monitor", "Monitor"),
                    ("reject", "Reject"),
                    (None, "Unscored"),
                )
                if bands[key]
            ],
        )
    )
    histogram = Counter(_bucket(s) for s in scores)
    board.tables.append(
        Table(
            "score_distribution",
            "Score distribution",
            f"Priority scores of leads qualified in {when}, in steps of ten.",
            ["Leads"],
            [Row(_bucket(Decimal(b)), [histogram[_bucket(Decimal(b))]]) for b in range(0, 100, 10)]
            if scores
            else [],
        )
    )

    def top(values: list[str | None], unknown: str) -> list[Row]:
        counts = Counter(v for v in values if v)
        rows = [Row(k, [n]) for k, n in counts.most_common(TOP)]
        missing = sum(1 for v in values if not v)
        return rows + ([Row(unknown, [missing])] if missing else [])

    industries = [a.industry for _, a in leads]
    countries = [
        COUNTRY_NAMES.get(a.hq_country, a.hq_country) if a.hq_country else None for _, a in leads
    ]
    board.tables += [
        Table(
            "industries",
            "Top industries",
            f"Industries of the companies whose leads were qualified in {when}.",
            ["Leads"],
            top(industries, "Industry unknown"),
        ),
        Table(
            "geographies",
            "Top countries",
            f"Countries of the companies whose leads were qualified in {when}.",
            ["Leads"],
            top(countries, "Country unknown"),
        ),
    ]

    signal_rows = await db.execute(
        select(Observation.value, ResearchRun.normalised_domain)
        .join(ResearchRun, ResearchRun.id == Observation.research_run_id)
        .join(Evidence, Evidence.id == Observation.evidence_id)
        .where(
            Observation.area == ObservationArea.SIGNALS,
            _between(func.coalesce(Evidence.published_at, Evidence.collected_at), start, end),
        )
    )
    signal_companies: dict[str, set[str]] = defaultdict(set)
    for value, domain in signal_rows.all():
        kind = (value or {}).get("signal")
        if kind:
            signal_companies[kind].add(domain)
    board.tables.append(
        Table(
            "signals",
            "Top buying signals",
            f"Dated buying signals published in {when}, by the number of companies showing each.",
            ["Companies"],
            [
                Row(SIGNAL_LABELS.get(k, k.replace("_", " ").capitalize()), [len(v)])
                for k, v in sorted(signal_companies.items(), key=lambda kv: -len(kv[1]))[:TOP]
            ],
        )
    )

    opportunity_types = (
        await db.execute(
            _scoped(
                select(OpportunityCategory.name, func.count())
                .select_from(Opportunity)
                .join(Account, Account.id == Opportunity.account_id)
                .outerjoin(OpportunityCategory, OpportunityCategory.id == Opportunity.category_id)
                .where(
                    Opportunity.deleted_at.is_(None),
                    _between(Opportunity.created_at, start, end),
                )
                .group_by(OpportunityCategory.name),
                user,
            )
        )
    ).all()
    board.tables.append(
        Table(
            "opportunity_types",
            "Opportunity types",
            f"Opportunities created in {when}, by category.",
            ["Opportunities"],
            [
                Row(name or "No category", [n])
                for name, n in sorted(opportunity_types, key=lambda r: -r[1])[:TOP]
            ],
        )
    )

    # ICP performance: does a higher ICP score lead to deals and wins?
    account_ids = {a.id for _, a in leads}
    deals_by_account: dict[uuid.UUID, list[StageOutcome]] = defaultdict(list)
    if account_ids:
        for account_id, outcome in (
            await db.execute(
                select(Deal.account_id, Deal.outcome).where(
                    Deal.account_id.in_(account_ids), Deal.deleted_at.is_(None)
                )
            )
        ).all():
            deals_by_account[account_id].append(outcome)
    icp: dict[str, list[int]] = {b: [0, 0, 0] for b in (ICP_HIGH, ICP_MID, ICP_LOW, "Unknown ICP")}
    seen: set[uuid.UUID] = set()
    for _, account in leads:
        if account.id in seen:
            continue
        seen.add(account.id)
        cells = icp[_icp_band(account.icp_score)]
        outcomes = deals_by_account.get(account.id, [])
        cells[0] += 1
        cells[1] += 1 if outcomes else 0
        cells[2] += 1 if StageOutcome.WON in outcomes else 0
    board.tables.append(
        Table(
            "icp_performance",
            "ICP performance",
            f"Companies whose leads were qualified in {when}, by ICP score: how many have "
            "a deal and how many have won one so far.",
            ["Companies", "With a deal", "Won"],
            [Row(band, list(cells)) for band, cells in icp.items() if cells[0]],
        )
    )
    return board


# --- management --------------------------------------------------------------------------------


def _probability(deal: Deal, stage: PipelineStage) -> float | None:
    probability = deal.probability if deal.probability is not None else stage.probability
    return None if probability is None else float(probability)


def _deals_note(n: int, what: str) -> str:
    return f"{n} {what} {'deal' if n == 1 else 'deals'}"


def _money_cell(rows: Iterable[tuple[Decimal | None, str]]) -> list[Money]:
    return _money_by_currency(rows)[0]


async def management(db: AsyncSession, *, user: User, period: Period) -> Dashboard:
    start, end = window(period)
    when = PERIOD_LABELS[period]
    board = Dashboard(period, start, end)
    today = _now().date()

    open_deals = await _deals(db, user, Deal.outcome == StageOutcome.OPEN)
    won = await _deals(db, user, *_closed_in(start, end, StageOutcome.WON))
    lost = await _deals(db, user, *_closed_in(start, end, StageOutcome.LOST))
    values, weights = _deal_rows((d, s) for d, _, s, _ in open_deals)
    board.figures += _money_figures(
        "pipeline",
        "Open pipeline",
        "The value of every open deal today, as entered by a person.",
        values,
        "/pipeline",
    )
    board.figures += _money_figures(
        "weighted_pipeline",
        "Weighted pipeline",
        "Each open deal's value times its probability. Deals without a value or a probability "
        "are left out.",
        [w for w in weights if w[0] is not None],
        "/pipeline",
    )
    board.figures += _money_figures(
        "won_value",
        "Won",
        f"The value of deals won in {when}.",
        [(d.value, d.currency) for d, *_ in won],
        "/pipeline",
    )
    won_known, _ = _money_by_currency((d.value, d.currency) for d, *_ in won)
    won_counts = Counter(d.currency for d, *_ in won if d.value is not None)
    for m in won_known:
        board.figures.append(
            Figure(
                "average_deal" if len(won_known) == 1 else f"average_deal_{m.currency.lower()}",
                "Average won deal" if len(won_known) == 1 else f"Average won deal ({m.currency})",
                float(m.amount / won_counts[m.currency]),
                "money",
                f"The mean value of deals won in {when} that have a value.",
                m.currency,
                _deals_note(won_counts[m.currency], "won"),
            )
        )
    if not won_known:
        board.figures.append(
            Figure(
                "average_deal",
                "Average won deal",
                None,
                "money",
                f"The mean value of deals won in {when} that have a value.",
                "GBP",
                "No won deal with a value yet",
            )
        )
    board.figures.append(
        Figure(
            "win_rate",
            "Win rate",
            _pct(len(won), len(won) + len(lost)),
            "percent",
            f"Deals won out of deals won or lost in {when}.",
            detail=_of(len(won), len(won) + len(lost)) + " closed deals",
        )
    )

    soon = today + timedelta(days=LIKELY_CLOSE_DAYS)
    likely = sorted(
        (
            (d, a, s, p)
            for d, a, s, p in open_deals
            if d.expected_close is not None and today <= d.expected_close <= soon
        ),
        key=lambda r: (r[0].expected_close, -(r[0].value or 0)),
    )
    owners = await _user_names(db, {d.owner_id for d, *_ in open_deals if d.owner_id})
    board.tables.append(
        Table(
            "likely_closes",
            "Likely closes",
            f"Open deals expected to close in the next {LIKELY_CLOSE_DAYS} days, soonest first.",
            ["Expected close", "Value", "Probability", "Owner"],
            [
                Row(
                    f"{a.name} · {d.name}",
                    [
                        d.expected_close.isoformat() if d.expected_close else None,
                        [Money(float(d.value), d.currency)] if d.value is not None else None,
                        _probability(d, s),
                        owners.get(d.owner_id) if d.owner_id else None,
                    ],
                    f"/pipeline?tab={p.key}",
                )
                for d, a, s, p in likely
            ],
        )
    )

    board.tables.append(await _salespeople(db, user, start, end, open_deals, won, lost, when))

    def closed_by(key_of: Any) -> dict[str, list[int]]:
        out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for d, a, *_ in won:
            out[key_of(d, a)][0] += 1
        for d, a, *_ in lost:
            out[key_of(d, a)][1] += 1
        return out

    by_industry = closed_by(lambda d, a: a.industry or "Industry unknown")
    board.tables.append(
        Table(
            "industries_that_convert",
            "Industries that convert",
            f"Deals won and lost in {when}, by the company's industry.",
            ["Won", "Lost", "Win rate"],
            [
                Row(k, [w, lo, _pct(w, w + lo)])
                for k, (w, lo) in sorted(by_industry.items(), key=lambda kv: (-kv[1][0], kv[0]))
            ],
        )
    )

    services = await _deal_services(db, [d for d, *_ in won])
    sold: dict[str, list[tuple[Decimal | None, str]]] = defaultdict(list)
    for d, *_ in won:
        sold[services.get(d.id) or "No service recorded"].append((d.value, d.currency))
    board.tables.append(
        Table(
            "services_that_sell",
            "Services that sell",
            f"Deals won in {when}, by the service of the opportunity they came from.",
            ["Won", "Value"],
            [
                Row(k, [len(v), _money_cell(v)])
                for k, v in sorted(sold.items(), key=lambda kv: (-len(kv[1]), kv[0]))
            ],
        )
    )

    board.tables.append(await _lead_sources(db, user, start, end, when))

    reasons = Counter(d.lost_reason for d, *_ in lost)
    board.tables.append(
        Table(
            "lost_reasons",
            "Why deals are lost",
            f"The reason given for each deal lost in {when}.",
            ["Deals", "Value"],
            [
                Row(
                    LOST_REASON_LABELS[r] if r else "No reason",
                    [n, _money_cell((d.value, d.currency) for d, *_ in lost if d.lost_reason == r)],
                )
                for r, n in reasons.most_common()
            ],
        )
    )
    at_risk = [
        v for v in await health.list_clients(db, user=user) if v.colour is not HealthColour.GREEN
    ]
    board.tables.append(
        Table(
            "clients_at_risk",
            "Clients at risk",
            "Right now, whatever the period: clients whose health is Red or Yellow, worst first, "
            "with the main reason.",
            ["Health", "Main reason", "Account manager"],
            [
                Row(
                    v.account.name,
                    [v.colour.value.capitalize(), v.reasons[0].text, v.manager_name or "Not set"],
                    href=f"/accounts/{v.account.id}?tab=client",
                )
                for v in at_risk
            ],
        )
    )
    expanding = [v for v in await health.list_clients(db, user=user) if v.expansion]
    board.tables.append(
        Table(
            "clients_with_expansion",
            "Clients with expansion potential",
            "Right now: clients with problems research found on their own site that nobody has "
            "opened or dismissed yet, each backed by evidence.",
            ["Suggestions", "Problems found", "Account manager"],
            [
                Row(
                    v.account.name,
                    [len(v.expansion), ", ".join(v.expansion), v.manager_name or "Not set"],
                    href=f"/accounts/{v.account.id}?tab=client",
                )
                for v in sorted(expanding, key=lambda v: (-len(v.expansion), v.account.name))
            ],
        )
    )
    board.tables.append(await _referrals(db, user))
    board.funnel = await funnel(db, user=user, start=start, end=end)
    return board


async def _referrals(db: AsyncSession, user: User) -> Table:
    """Who sends Verkies work, and whether it converts. All time, not the period."""
    by_referrer: dict[str, list[Any]] = defaultdict(list)
    for v in await referrals.list_referrals(db, user=user, limit=1000):
        by_referrer[v.referral.referrer_name].append(v)
    rows = []
    for name, views in sorted(by_referrer.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        converted = sum(1 for v in views if v.converted)
        revenue: list[tuple[Decimal | None, str]] = []
        for v in views:
            revenue += [(amount, currency) for currency, amount in v.revenue.items()]
        rows.append(
            Row(name, [len(views), converted, _pct(converted, len(views)), _money_cell(revenue)])
        )
    return Table(
        "referral_sources",
        "Referrals",
        "Every referral recorded, by who made it. Converted: a deal on the referred company was "
        "won after the referral. Revenue is those deals' values; deals without a value are "
        "left out.",
        ["Referrals", "Converted", "Conversion", "Revenue"],
        rows,
    )


async def _user_names(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).all())


async def _deal_services(db: AsyncSession, deals: list[Deal]) -> dict[uuid.UUID, str]:
    opp_ids = {d.opportunity_id for d in deals if d.opportunity_id}
    if not opp_ids:
        return {}
    names = dict(
        (
            await db.execute(
                select(Opportunity.id, Service.name)
                .join(Service, Service.id == Opportunity.service_id)
                .where(Opportunity.id.in_(opp_ids))
            )
        ).all()
    )
    return {d.id: names[d.opportunity_id] for d in deals if d.opportunity_id in names}


async def _salespeople(
    db: AsyncSession,
    user: User,
    start: datetime,
    end: datetime,
    open_deals: list[Any],
    won: list[Any],
    lost: list[Any],
    when: str,
) -> Table:
    stats: dict[uuid.UUID | None, dict[str, Any]] = defaultdict(
        lambda: {"open": [], "won": [], "lost": 0, "activities": 0, "overdue": 0}
    )
    for d, *_ in open_deals:
        stats[d.owner_id]["open"].append((d.value, d.currency))
    for d, *_ in won:
        stats[d.owner_id]["won"].append((d.value, d.currency))
    for d, *_ in lost:
        stats[d.owner_id]["lost"] += 1
    activity = await db.execute(
        _scoped(
            select(Activity.actor_id, func.count())
            .join(Account, Account.id == Activity.account_id)
            .where(_between(Activity.occurred_at, start, end))
            .group_by(Activity.actor_id),
            user,
        )
    )
    for actor, n in activity.all():
        stats[actor]["activities"] += n
    overdue = await db.execute(
        _scoped(
            select(Task.owner_id, func.count())
            .join(Account, Account.id == Task.account_id)
            .where(
                Task.deleted_at.is_(None),
                Task.status.in_((TaskStatus.OPEN, TaskStatus.IN_PROGRESS)),
                Task.due_at < _now(),
            )
            .group_by(Task.owner_id),
            user,
        )
    )
    for owner, n in overdue.all():
        stats[owner]["overdue"] += n
    names = await _user_names(db, {k for k in stats if k})
    rows = []
    for owner, s in sorted(
        stats.items(), key=lambda kv: (kv[0] is None, names.get(kv[0], "") if kv[0] else "")
    ):
        won_n, lost_n = len(s["won"]), s["lost"]
        rows.append(
            Row(
                names.get(owner, "Former member") if owner else "No owner",
                [
                    len(s["open"]),
                    _money_cell(s["open"]),
                    won_n,
                    _money_cell(s["won"]),
                    lost_n,
                    _pct(won_n, won_n + lost_n),
                    s["activities"],
                    s["overdue"],
                ],
            )
        )
    return Table(
        "salespeople",
        "Salesperson performance",
        f"Per deal owner: open deals and their value today; deals won and lost in {when}; "
        f"activities they logged in {when}; their overdue tasks today.",
        [
            "Open deals",
            "Open value",
            "Won",
            "Won value",
            "Lost",
            "Win rate",
            "Activities",
            "Overdue",
        ],
        rows,
    )


async def _lead_sources(
    db: AsyncSession, user: User, start: datetime, end: datetime, when: str
) -> Table:
    leads = (
        await db.execute(
            _scoped(
                select(Lead.source, Lead.account_id)
                .join(Account, Account.id == Lead.account_id)
                .where(Lead.deleted_at.is_(None), _between(Lead.qualified_at, start, end)),
                user,
            )
        )
    ).all()
    account_ids = {a for _, a in leads}
    outcomes: dict[uuid.UUID, set[StageOutcome]] = defaultdict(set)
    if account_ids:
        for account_id, outcome in (
            await db.execute(
                select(Deal.account_id, Deal.outcome).where(
                    Deal.account_id.in_(account_ids), Deal.deleted_at.is_(None)
                )
            )
        ).all():
            outcomes[account_id].add(outcome)
    by_source: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for source, account_id in leads:
        cells = by_source[_words(source) if source else "Unknown"]
        cells[0] += 1
        cells[1] += 1 if outcomes.get(account_id) else 0
        cells[2] += 1 if StageOutcome.WON in outcomes.get(account_id, set()) else 0
    return Table(
        "lead_sources",
        "Lead sources that work",
        f"Leads qualified in {when}, by where they came from: how many have a deal and how "
        "many have won one so far.",
        ["Qualified", "With a deal", "Won"],
        [Row(k, list(v)) for k, v in sorted(by_source.items(), key=lambda kv: -kv[1][0])],
    )
