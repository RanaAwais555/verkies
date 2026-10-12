"""Learned proposals for the scoring weights and ICP industry tiers (SCORING_SPEC.md §7, master
context §15; slice 5.3).

Worked out only from deal outcomes (what was true when each deal was won or lost), the same way
every time, so the same data gives the same proposal. Deliberately cautious:

- Nothing is proposed until there are `learning_min_sample` won *and* lost outcomes.
- Scoring weights: for each dimension, the correlation between its score when the lead was first
  scored and winning (point-biserial). Its weight moves by at most a quarter of itself in that
  direction (factor 1 + r/2, held to 0.75-1.25), then all weights are renormalised to sum to 1. A
  dimension known for too few won or lost deals keeps its weight.
- ICP: an industry with at least `learning_min_sample` closed deals whose win rate is at least
  15 points above the overall rate moves up one tier, at least 15 points below moves down one.

A proposal is never active by itself. Activating it saves a new config version through the same
validation and audit as the config editor, and is refused if the config changed in the meantime.
"""

import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.models import User
from app.config import get_settings
from app.core.enums import AuditSource, ProposalStatus, StageOutcome
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.learning.models import DealOutcome, LearnedProposal
from app.qualification.config import IcpConfigModel
from app.scoring import versions
from app.scoring.config import DIMENSIONS

MAX_STEP = 0.25  # a weight moves by at most this share of itself
TIER_GAP = 0.15  # win rate this far from the overall rate moves an industry one tier
TIER_ORDER = ("other", "B", "A", "S")
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


def _now() -> datetime:
    return datetime.now(UTC)


def correlation(pairs: list[tuple[float, bool]]) -> float:
    """Point-biserial correlation between a score and winning; 0 when either side is constant."""
    n = len(pairs)
    if n < 2:
        return 0.0
    xs = [x for x, _ in pairs]
    ys = [1.0 if won else 0.0 for _, won in pairs]
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def _round_weights(raw: dict[str, float]) -> dict[str, float]:
    """To two decimals, summing exactly to 1: whole hundredths first, then the spare hundredths to
    the weights that rounding cut most (largest remainder), so no weight absorbs the error."""
    total = sum(raw.values())
    exact = {k: v / total * 100 for k, v in raw.items()}
    cents = {k: math.floor(v) for k, v in exact.items()}
    spare = 100 - sum(cents.values())
    for k in sorted(exact, key=lambda k: (-(exact[k] - cents[k]), k))[:spare]:
        cents[k] += 1
    return {k: c / 100 for k, c in cents.items()}


@dataclass
class Draft:
    config: dict[str, Any]
    changes: list[dict[str, Any]]
    basis: dict[str, Any]


def _basis(outcomes: list[DealOutcome], version: int) -> dict[str, Any]:
    digest = hashlib.sha256(
        "".join(
            f"{o.id}:{o.outcome.value};" for o in sorted(outcomes, key=lambda o: str(o.id))
        ).encode()
    ).hexdigest()
    won = sum(1 for o in outcomes if o.outcome is StageOutcome.WON)
    return {
        "outcomes": len(outcomes),
        "won": won,
        "lost": len(outcomes) - won,
        "config_version": version,
        "digest": digest,
    }


def _enough(outcomes: list[DealOutcome], min_sample: int) -> None:
    won = sum(1 for o in outcomes if o.outcome is StageOutcome.WON)
    lost = len(outcomes) - won
    if won < min_sample or lost < min_sample:
        raise ValidationFailed(
            f"Not enough closed deals to learn from: {won} won and {lost} lost, and at least "
            f"{min_sample} of each are needed.",
            code="not_enough_outcomes",
            details={"won": won, "lost": lost, "needed": min_sample},
        )


def draft_scoring(
    outcomes: list[DealOutcome], current: dict[str, Any], version: int, min_sample: int
) -> Draft:
    _enough(outcomes, min_sample)
    weights: dict[str, float] = current["weights"]
    raw: dict[str, float] = {}
    evidence: dict[str, dict[str, Any]] = {}
    for dim in DIMENSIONS:
        pairs = [
            (float(o.first_scores[dim]), o.outcome is StageOutcome.WON)
            for o in outcomes
            if o.first_scores and o.first_scores.get(dim) is not None
        ]
        won = [x for x, w in pairs if w]
        lost = [x for x, w in pairs if not w]
        if len(won) < min_sample or len(lost) < min_sample:
            raw[dim] = weights[dim]
            evidence[dim] = {"known_won": len(won), "known_lost": len(lost), "r": None}
            continue
        r = correlation(pairs)
        factor = min(1 + MAX_STEP, max(1 - MAX_STEP, 1 + r / 2))
        raw[dim] = weights[dim] * factor
        evidence[dim] = {
            "known_won": len(won),
            "known_lost": len(lost),
            "r": round(r, 3),
            "won_mean": round(sum(won) / len(won), 1),
            "lost_mean": round(sum(lost) / len(lost), 1),
        }
    proposed = _round_weights(raw)
    changes = []
    for dim in DIMENSIONS:
        if proposed[dim] == round(weights[dim], 2):
            continue
        e = evidence[dim]
        if e["r"] is None:
            why = "Kept in proportion while other weights moved."
        else:
            why = (
                f"Won deals first scored {e['won_mean']} on average against {e['lost_mean']} for "
                f"lost ({e['known_won']} won, {e['known_lost']} lost; correlation {e['r']})."
            )
        changes.append(
            {
                "key": dim,
                "label": DIMENSION_LABELS[dim],
                "from": round(weights[dim], 2),
                "to": proposed[dim],
                "why": why,
                **e,
            }
        )
    config = {**current, "weights": proposed}
    return Draft(config=config, changes=changes, basis=_basis(outcomes, version))


def draft_icp(
    outcomes: list[DealOutcome], current: dict[str, Any], version: int, min_sample: int
) -> Draft:
    _enough(outcomes, min_sample)
    model = IcpConfigModel.model_validate(current)
    known = [o for o in outcomes if o.industry]
    overall = sum(1 for o in known if o.outcome is StageOutcome.WON) / len(known) if known else 0
    tiers = {tier: list(names) for tier, names in model.industry_tiers.items()}
    changes = []
    for industry in sorted({o.industry for o in known if o.industry}):
        deals = [o for o in known if o.industry == industry]
        if len(deals) < min_sample:
            continue
        won = sum(1 for o in deals if o.outcome is StageOutcome.WON)
        rate = won / len(deals)
        tier = model.tier_of(industry) or "other"
        step = 1 if rate - overall >= TIER_GAP else -1 if overall - rate >= TIER_GAP else 0
        position = TIER_ORDER.index(tier) if tier in TIER_ORDER else None
        if step == 0 or position is None:
            continue
        target_position = position + step
        if not 0 <= target_position < len(TIER_ORDER):
            continue
        target = TIER_ORDER[target_position]
        if tier != "other":
            tiers[tier] = [n for n in tiers[tier] if n != industry]
        if target != "other":
            tiers.setdefault(target, []).append(industry)
        changes.append(
            {
                "key": industry,
                "label": industry.capitalize(),
                "from": tier,
                "to": target,
                "won": won,
                "lost": len(deals) - won,
                "win_rate": round(rate, 3),
                "overall": round(overall, 3),
                "why": f"Won {won} of {len(deals)} ({round(rate * 100)}%) against "
                f"{round(overall * 100)}% across all industries.",
            }
        )
    config = {**current, "industry_tiers": tiers}
    return Draft(config=config, changes=changes, basis=_basis(outcomes, version))


async def current_outcomes(db: AsyncSession) -> list[DealOutcome]:
    """Every outcome that stands, across the whole team: the configuration is shared."""
    return list(
        (
            await db.execute(
                select(DealOutcome)
                .where(DealOutcome.superseded_at.is_(None))
                .order_by(DealOutcome.closed_at, DealOutcome.id)
            )
        ).scalars()
    )


async def draft(db: AsyncSession, kind: str) -> Draft:
    active = await versions.active_version(db, kind)
    if active is None:
        raise NotFound(f"There is no active {kind} configuration.")
    outcomes = await current_outcomes(db)
    min_sample = get_settings().learning_min_sample
    make = draft_scoring if kind == "scoring" else draft_icp
    return make(outcomes, active.config, active.version, min_sample)


async def propose(db: AsyncSession, *, user: User, kind: str) -> LearnedProposal:
    found = await draft(db, kind)
    if not found.changes:
        raise ValidationFailed(
            "The outcomes support the current configuration: nothing to change.",
            code="no_change",
            details=found.basis,
        )
    await db.execute(
        update(LearnedProposal)
        .where(LearnedProposal.kind == kind, LearnedProposal.status == ProposalStatus.PROPOSED)
        .values(status=ProposalStatus.SUPERSEDED)
    )
    proposal = LearnedProposal(
        kind=kind,
        based_on_version=found.basis["config_version"],
        proposed_config=found.config,
        changes=found.changes,
        basis=found.basis,
        created_by_id=user.id,
    )
    db.add(proposal)
    await db.flush()
    audit.record(
        db,
        action=f"proposal.{kind}.created",
        object_table="learned_proposals",
        object_id=proposal.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"changes": len(found.changes), **found.basis},
    )
    await db.commit()
    return proposal


async def _open(db: AsyncSession, proposal_id: uuid.UUID) -> LearnedProposal:
    proposal = await db.get(LearnedProposal, proposal_id, with_for_update=True)
    if proposal is None:
        raise NotFound("Proposal not found.")
    if proposal.status is not ProposalStatus.PROPOSED:
        raise Conflict(f"This proposal was already {proposal.status.value}.")
    return proposal


async def activate(
    db: AsyncSession, *, user: User, proposal_id: uuid.UUID, note: str | None
) -> LearnedProposal:
    proposal = await _open(db, proposal_id)
    active = await versions.active_version(db, proposal.kind)
    if active is None or active.version != proposal.based_on_version:
        raise Conflict(
            "The configuration changed after this proposal was made. Make a new proposal.",
            code="stale",
        )
    row = await versions.save_version(
        db,
        kind=proposal.kind,
        config=proposal.proposed_config,
        note=(note or "").strip() or f"Learned from {proposal.basis['outcomes']} closed deals",
        actor=user,
        reason=f"Activated learned proposal {proposal.id}",
    )
    proposal.status = ProposalStatus.ACTIVATED
    proposal.decided_by_id = user.id
    proposal.decided_at = _now()
    proposal.decision_note = (note or "").strip() or None
    proposal.activated_version = row.version
    audit.record(
        db,
        action=f"proposal.{proposal.kind}.activated",
        object_table="learned_proposals",
        object_id=proposal.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"config_version": row.version},
        reason=proposal.decision_note,
    )
    await db.commit()
    return proposal


async def dismiss(
    db: AsyncSession, *, user: User, proposal_id: uuid.UUID, reason: str
) -> LearnedProposal:
    proposal = await _open(db, proposal_id)
    proposal.status = ProposalStatus.DISMISSED
    proposal.decided_by_id = user.id
    proposal.decided_at = _now()
    proposal.decision_note = reason.strip()
    audit.record(
        db,
        action=f"proposal.{proposal.kind}.dismissed",
        object_table="learned_proposals",
        object_id=proposal.id,
        user_id=user.id,
        source=AuditSource.API,
        reason=proposal.decision_note,
    )
    await db.commit()
    return proposal
