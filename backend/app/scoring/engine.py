"""Priority score, gates, bands and qualification (SCORING_SPEC.md §4-6).

Deterministic: the same facts and config always give the same score. The breakdown records
every input, weight, contribution, Unknown dimension and gate, so any score can be explained.
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import PriorityBand
from app.intelligence.facts import Facts
from app.opportunities.detectors import Candidate
from app.qualification.config import IcpConfigModel
from app.qualification.icp import IcpInputs, IcpResult, evaluate
from app.scoring import dimensions as dim
from app.scoring.config import DIMENSIONS, ScoringConfigModel


@dataclass
class Assessment:
    scores: dict[str, float | None]
    priority_score: float | None
    priority_band: PriorityBand | None
    qualifies: bool
    not_qualified_because: list[str]
    icp: IcpResult
    service_key: str | None
    breakdown: dict[str, Any] = field(default_factory=dict)


def assess(
    facts: Facts,
    candidates: list[Candidate],
    *,
    solved_by: dict[str, list[str]],
    icp_config: IcpConfigModel,
    scoring_config: ScoringConfigModel,
    suppressed_by: str | None = None,
    possible_duplicates: list[str] | None = None,
    client_similarity: dim.Dimension | None = None,
) -> Assessment:
    strength = dim.evidence_strength(facts)
    buyer = dim.buyer_confidence(facts)
    fit, service_key = dim.service_fit(candidates, solved_by)
    icp = evaluate(
        IcpInputs(
            facts=facts,
            candidates=candidates,
            evidence_strength=strength,
            buyer_confidence=buyer,
            has_service_fit=service_key is not None,
            suppressed_by=suppressed_by,
            possible_duplicates=possible_duplicates or [],
        ),
        icp_config,
    )
    dims: dict[str, dim.Dimension] = {
        "icp_score": dim.Dimension(icp.icp_fit, note=icp.explanation),
        "opportunity_score": dim.opportunity(candidates, icp_config.min_opportunity_confidence),
        "intent_score": dim.intent(facts),
        "buyer_confidence": buyer,
        "data_confidence": dim.data_confidence(facts),
        "service_fit": fit,
        "timing_score": dim.timing(facts),
        "commercial_potential": dim.commercial_potential(facts, icp.industry_tier),
        # Reference-project profiles are not complete yet: Unknown until slice 1.5 can compare.
        "client_similarity": client_similarity
        or dim.Dimension(None, note="No complete reference-project profile to compare"),
        "evidence_strength": strength,
    }
    priority, gates, coverage = _priority(dims, icp, scoring_config)
    qualifies, reasons = _qualifies(facts, candidates, dims, icp, scoring_config)
    band = _band(priority, qualifies, scoring_config)
    breakdown = {
        "dimensions": {
            name: {
                "score": d.score,
                "weight": scoring_config.weights[name],
                "contribution": None
                if d.score is None
                else round(scoring_config.weights[name] * d.score, 2),
                "evidence_ids": d.evidence_ids,
                "note": d.note,
            }
            for name, d in dims.items()
        },
        "unknown": [name for name, d in dims.items() if d.score is None],
        "coverage": coverage,
        "gates": gates,
        "qualifies": qualifies,
        "not_qualified_because": reasons,
    }
    return Assessment(
        scores={name: d.score for name, d in dims.items()},
        priority_score=priority,
        priority_band=band,
        qualifies=qualifies,
        not_qualified_because=reasons,
        icp=icp,
        service_key=service_key,
        breakdown=breakdown,
    )


def _priority(
    dims: dict[str, dim.Dimension], icp: IcpResult, config: ScoringConfigModel
) -> tuple[float | None, list[dict[str, Any]], float]:
    weights = config.weights
    known = [n for n in DIMENSIONS if dims[n].score is not None]
    coverage = round(sum(weights[n] for n in known) / sum(weights.values()), 3)
    if not known:
        return None, [], coverage
    raw = sum(weights[n] * (dims[n].score or 0) for n in known) / sum(weights[n] for n in known)
    priority = raw
    gates: list[dict[str, Any]] = []
    g = config.gates

    def cap(name: str, limit: float, why: str) -> None:
        nonlocal priority
        applied = priority > limit
        priority = min(priority, limit)
        gates.append({"gate": name, "cap": limit, "applied": applied, "why": why})

    if icp.hard_reject:
        cap("hard_reject", g.hard_reject_cap, f"Rejected: {icp.rejection_reason}")
    if coverage < g.min_coverage:
        cap("coverage", g.low_coverage_cap, f"Only {coverage:.0%} of the weight is known")
    strength = dims["evidence_strength"].score or 0
    opportunity_evidence = bool(dims["opportunity_score"].evidence_ids)
    if strength < g.min_evidence_strength or not opportunity_evidence:
        cap(
            "evidence",
            g.low_evidence_cap,
            "Weak evidence"
            if strength < g.min_evidence_strength
            else "Opportunity has no evidence",
        )
    if not dims["service_fit"].score:
        cap("service", g.no_service_cap, "No Verkies service matches")
    if (dims["data_confidence"].score or 0) < g.min_data_confidence:
        cap("data_confidence", g.low_data_cap, "Too little verified account data")
    return round(priority, 2), gates, coverage


def _qualifies(
    facts: Facts,
    candidates: list[Candidate],
    dims: dict[str, dim.Dimension],
    icp: IcpResult,
    config: ScoringConfigModel,
) -> tuple[bool, list[str]]:
    q = config.qualification
    reasons: list[str] = []
    if icp.hard_reject:
        reasons.append(f"rejected by negative ICP ({icp.rejection_reason})")
    if icp.icp_fit is None or icp.icp_fit < q.min_icp:
        reasons.append(f"ICP fit below {q.min_icp:g}")
    if not any(c.evidence_ids for c in candidates):
        reasons.append("no evidenced opportunity")
    if (dims["evidence_strength"].score or 0) < q.min_evidence_strength:
        reasons.append(f"evidence strength below {q.min_evidence_strength:g}")
    if (dims["data_confidence"].score or 0) < q.min_data_confidence:
        reasons.append(f"data confidence below {q.min_data_confidence:g}")
    if (
        not dim.has_strong_signal(facts)
        and dim.problem_signal_count(candidates) < q.min_problem_signals
    ):
        reasons.append(
            "no strong buying signal and fewer than "
            f"{q.min_problem_signals} independent problem signals"
        )
    if not dims["service_fit"].score:
        reasons.append("no matching Verkies service")
    return not reasons, reasons


def _band(
    priority: float | None, qualifies: bool, config: ScoringConfigModel
) -> PriorityBand | None:
    if priority is None:
        return None
    b = config.bands
    if priority >= b.hot:
        band = PriorityBand.HOT
    elif priority >= b.high:
        band = PriorityBand.HIGH
    elif priority >= b.qualified:
        band = PriorityBand.QUALIFIED
    elif priority >= b.monitor:
        band = PriorityBand.MONITOR
    else:
        band = PriorityBand.REJECT
    if band in (PriorityBand.HOT, PriorityBand.HIGH) and not qualifies:
        return PriorityBand.QUALIFIED  # SCORING_SPEC.md §5: hot/high need qualification
    return band
