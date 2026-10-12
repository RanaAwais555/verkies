"""Win/loss analysis (master context §13, §15; slice 5.2).

Read only from deal outcomes (what was true when each deal closed, slice 5.1) and the feedback
given before the close. Every figure carries its sample size; a group with fewer closed deals than
`learning_min_sample` gets no win rate and is marked too few to learn from, so nobody reads a
pattern into two deals. Unknown values are their own group, never folded into another.
"""

import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account
from app.auth.models import User
from app.catalogue.models import Service
from app.config import get_settings
from app.core.enums import StageOutcome
from app.deals.service import LOST_REASON_LABELS
from app.leads.ranking import SIGNAL_LABELS
from app.learning.labels import FEEDBACK_LABELS
from app.learning.models import DealOutcome, SalesFeedback
from app.opportunities.models import OpportunityCategory

UNKNOWN = "Unknown"
# Priority at first scoring, by the default band boundaries (SCORING_SPEC.md §6).
PRIORITY_RANGES = (
    (90, "90 and over"),
    (75, "75 to 89"),
    (60, "60 to 74"),
    (40, "40 to 59"),
    (0, "Under 40"),
)


@dataclass
class Group:
    label: str
    won: int = 0
    lost: int = 0
    won_value: dict[str, Decimal] = field(default_factory=dict)
    won_unknown_value: int = 0
    won_days: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.won + self.lost

    def add(self, o: DealOutcome) -> None:
        if o.outcome is StageOutcome.WON:
            self.won += 1
            self.won_days.append(o.deal_days)
            if o.value is None:
                self.won_unknown_value += 1
            else:
                self.won_value[o.currency] = self.won_value.get(o.currency, Decimal(0)) + o.value
        else:
            self.lost += 1


def win_rate(won: int, total: int, min_sample: int) -> float | None:
    """None when there are too few closed deals to say anything."""
    return None if total < min_sample or total == 0 else won / total


@dataclass
class Dimension:
    key: str
    label: str
    groups: list[Group]


@dataclass
class SignalRow:
    signal: str
    label: str
    with_signal: Group
    without_signal: Group


@dataclass
class Analysis:
    since: datetime | None
    min_sample: int
    overall: Group
    late: int
    dimensions: list[Dimension]
    signals: list[SignalRow]
    lost_reasons: list[tuple[str, int]]
    feedback: list[Group]


def _words(value: str | None) -> str:
    return value.replace("_", " ").capitalize() if value else UNKNOWN


def _priority(o: DealOutcome) -> str:
    score = (o.first_scores or {}).get("priority_score")
    if score is None:
        return UNKNOWN
    return next(label for floor, label in PRIORITY_RANGES if score >= floor)


def _grouped(outcomes: Iterable[DealOutcome], key: Callable[[DealOutcome], str]) -> list[Group]:
    groups: dict[str, Group] = {}
    for o in outcomes:
        name = key(o) or UNKNOWN
        groups.setdefault(name, Group(name)).add(o)
    return sorted(groups.values(), key=lambda g: (g.label == UNKNOWN, -g.total, -g.won, g.label))


async def analyse(
    db: AsyncSession,
    *,
    user: User,
    months: int | None = 12,
    pipeline: str | None = None,
    now: datetime | None = None,
) -> Analysis:
    settings = get_settings()
    since = (now or datetime.now(UTC)) - timedelta(days=30 * months) if months else None
    stmt = (
        select(DealOutcome)
        .join(Account, Account.id == DealOutcome.account_id)
        .where(DealOutcome.superseded_at.is_(None), Account.deleted_at.is_(None))
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    if since is not None:
        stmt = stmt.where(DealOutcome.closed_at >= since)
    if pipeline:
        stmt = stmt.where(DealOutcome.pipeline_key == pipeline)
    outcomes = list((await db.execute(stmt.order_by(DealOutcome.closed_at))).scalars())

    overall = Group("All closed deals")
    for o in outcomes:
        overall.add(o)

    services: dict[uuid.UUID | None, str] = dict(
        (await db.execute(select(Service.id, Service.name))).all()
    )
    categories: dict[uuid.UUID | None, str] = dict(
        (await db.execute(select(OpportunityCategory.id, OpportunityCategory.name))).all()
    )
    dimensions = [
        Dimension(
            "service", "Service", _grouped(outcomes, lambda o: services.get(o.service_id, UNKNOWN))
        ),
        Dimension(
            "opportunity_type",
            "Opportunity type",
            _grouped(outcomes, lambda o: categories.get(o.category_id, UNKNOWN)),
        ),
        Dimension("industry", "Industry", _grouped(outcomes, lambda o: _words(o.industry))),
        Dimension(
            "size", "Company size", _grouped(outcomes, lambda o: o.company_size_band or UNKNOWN)
        ),
        Dimension("country", "Country", _grouped(outcomes, lambda o: o.hq_country or UNKNOWN)),
        Dimension("source", "Lead source", _grouped(outcomes, lambda o: _words(o.source))),
        Dimension("buyer_role", "Buyer role", _grouped(outcomes, lambda o: _words(o.buyer_role))),
        Dimension("priority", "Priority when first scored", _grouped(outcomes, _priority)),
    ]

    kinds = sorted({s["signal"] for o in outcomes for s in (o.signals or []) if s.get("signal")})
    signals = []
    for kind in kinds:
        row = SignalRow(
            kind, SIGNAL_LABELS.get(kind, _words(kind)), Group("With"), Group("Without")
        )
        for o in outcomes:
            seen = any(s.get("signal") == kind for s in (o.signals or []))
            (row.with_signal if seen else row.without_signal).add(o)
        signals.append(row)
    signals.sort(key=lambda r: (-r.with_signal.total, r.label))

    lost: dict[str, int] = defaultdict(int)
    for o in outcomes:
        if o.outcome is StageOutcome.LOST:
            lost[LOST_REASON_LABELS[o.lost_reason] if o.lost_reason else "No reason given"] += 1

    feedback = await _feedback(db, outcomes)
    return Analysis(
        since=since,
        min_sample=settings.learning_min_sample,
        overall=overall,
        late=sum(1 for o in outcomes if o.captured_late),
        dimensions=dimensions,
        signals=signals,
        lost_reasons=sorted(lost.items(), key=lambda kv: (-kv[1], kv[0])),
        feedback=feedback,
    )


async def _feedback(db: AsyncSession, outcomes: list[DealOutcome]) -> list[Group]:
    """How deals did on accounts that had each kind of feedback before the deal closed."""
    by_account: dict[uuid.UUID, list[DealOutcome]] = defaultdict(list)
    for o in outcomes:
        by_account[o.account_id].append(o)
    if not by_account:
        return []
    groups: dict[str, Group] = {}
    counted: set[tuple[str, uuid.UUID]] = set()
    rows: Any = await db.execute(
        select(SalesFeedback).where(SalesFeedback.account_id.in_(list(by_account)))
    )
    for f in rows.scalars():
        label = FEEDBACK_LABELS[f.kind]
        for o in by_account[f.account_id]:
            if f.created_at > o.closed_at or (label, o.id) in counted:
                continue
            counted.add((label, o.id))
            groups.setdefault(label, Group(label)).add(o)
    return sorted(groups.values(), key=lambda g: (-g.total, g.label))
