"""Opportunities, ICP and scoring on golden fixture sites (SCORING_SPEC.md §8), plus each
gate, band boundary and config rule on its own."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.catalogue.defaults import solved_by
from app.core.enums import PriorityBand, RejectionReason
from app.intelligence.facts import Fact, Facts, facts_from_observations
from app.intelligence.runner import analyse
from app.opportunities.detectors import Candidate, detect
from app.qualification.config import IcpConfigModel
from app.scoring.config import ScoringConfigModel
from app.scoring.engine import Assessment, _band, assess
from tests.fixtures.sites import AGENCY, CLOSED, FREELANCER, HOLDING, IMMIGRATION, PARKED, SAAS


def assess_site(fixture: tuple[Any, Any], **kw: Any) -> tuple[list[Candidate], Assessment]:
    facts = facts_from_observations(analyse(*fixture)[0])
    candidates = detect(facts)
    return candidates, assess(
        facts,
        candidates,
        solved_by=solved_by(),
        icp_config=IcpConfigModel(),
        scoring_config=ScoringConfigModel(),
        **kw,
    )


# --- golden fixtures ----------------------------------------------------------------------


def test_service_firm_with_manual_intake_is_high_priority() -> None:
    candidates, a = assess_site(IMMIGRATION)
    categories = [c.category for c in candidates]
    assert {"website_rebuild", "crm", "seo", "booking_system"} <= set(categories)
    crm = next(c for c in candidates if c.category == "crm")
    assert "an immigration business" in crm.problem and "generic contact form" in crm.problem
    assert crm.evidence_ids  # every candidate cites its evidence
    assert a.qualifies and a.priority_band == PriorityBand.HIGH
    assert 75 <= (a.priority_score or 0) < 90
    assert a.icp.industry_tier == "A" and not a.icp.hard_reject
    assert a.scores["intent_score"] is None  # nothing says they are changing now: Unknown
    assert a.scores["client_similarity"] is None


def test_saas_hiring_engineers_qualifies_but_unknown_buyer_holds_it_back() -> None:
    candidates, a = assess_site(SAAS)
    assert candidates[0].category == "ongoing_product_support"
    assert a.scores["intent_score"] == 90 and a.scores["timing_score"] == 75
    assert a.scores["buyer_confidence"] == 15
    assert a.qualifies and a.priority_band == PriorityBand.QUALIFIED
    assert any(h.rule_id == "no_reachable_buyer" for h in a.icp.hits)


def test_holding_page_is_rejected_with_reasons() -> None:
    candidates, a = assess_site(HOLDING)
    assert [c.category for c in candidates] == ["mvp_development"]
    assert a.priority_band == PriorityBand.REJECT and not a.qualifies
    assert "ICP fit below 50" in a.not_qualified_because


@pytest.mark.parametrize(
    ("fixture", "rule", "reason"),
    [
        (PARKED, "parked_domain", RejectionReason.INACTIVE_COMPANY),
        (CLOSED, "closed", RejectionReason.INACTIVE_COMPANY),
        (FREELANCER, "personal_site", RejectionReason.STUDENT_OR_FREELANCER),
        (AGENCY, "agency", RejectionReason.COMPETITOR),
    ],
)
def test_negative_icp_hard_rejects(
    fixture: tuple[Any, Any], rule: str, reason: RejectionReason
) -> None:
    _, a = assess_site(fixture)
    assert a.icp.hard_reject and a.icp.rejection_reason == reason
    hit = next(h for h in a.icp.hits if h.rule_id == rule)
    assert hit.severity == "hard" and hit.evidence_ids
    assert (a.priority_score or 0) <= 39 and a.priority_band == PriorityBand.REJECT
    assert not a.qualifies


def test_agency_is_flagged_for_partnership_routing() -> None:
    _, a = assess_site(AGENCY)
    assert a.icp.is_agency
    assert "partnership" in next(h.note for h in a.icp.hits if h.rule_id == "agency")


def test_parked_and_closed_sites_get_no_opportunities() -> None:
    for fixture in (PARKED, CLOSED):
        candidates, _ = assess_site(fixture)
        assert candidates == []


def test_suppressed_domain_is_rejected_and_duplicate_only_flagged() -> None:
    _, suppressed = assess_site(IMMIGRATION, suppressed_by="domain harbourimmigration.co.uk")
    assert suppressed.icp.rejection_reason == RejectionReason.SUPPRESSED_ACCOUNT
    _, duplicate = assess_site(IMMIGRATION, possible_duplicates=["acc-1"])
    hit = next(h for h in duplicate.icp.hits if h.rule_id == "duplicate")
    assert hit.severity == "review" and not duplicate.icp.hard_reject


def test_assessment_is_deterministic() -> None:
    _, first = assess_site(IMMIGRATION)
    _, second = assess_site(IMMIGRATION)
    assert first.breakdown == second.breakdown


def test_breakdown_explains_every_dimension() -> None:
    _, a = assess_site(IMMIGRATION)
    dims = a.breakdown["dimensions"]
    assert set(dims) == set(ScoringConfigModel().weights)
    for name, entry in dims.items():
        assert entry["note"], name
        if entry["score"] is None:
            assert name in a.breakdown["unknown"]


# --- gates and bands in isolation ---------------------------------------------------------


def _facts(*items: tuple[str, Any]) -> Facts:
    return Facts(Fact(k, v, 0.9, f"e{i}", f"https://x.test/{i}") for i, (k, v) in enumerate(items))


def _candidate(category: str = "crm", confidence: float = 0.7) -> Candidate:
    return Candidate(category, "T", "P", confidence, "rule", ["e0"], ["a", "b"])


def test_unknown_dimensions_are_excluded_not_zeroed() -> None:
    facts = _facts(("company.industry", {"name": "saas"}))
    a = assess(
        facts,
        [_candidate()],
        solved_by=solved_by(),
        icp_config=IcpConfigModel(),
        scoring_config=ScoringConfigModel(),
    )
    assert a.scores["timing_score"] is None and "timing_score" in a.breakdown["unknown"]
    assert a.breakdown["dimensions"]["timing_score"]["contribution"] is None
    assert a.breakdown["coverage"] < 1


def test_no_service_match_caps_priority() -> None:
    facts = facts_from_observations(analyse(*IMMIGRATION)[0])
    capped = assess(
        facts,
        detect(facts),
        solved_by={},
        icp_config=IcpConfigModel(),
        scoring_config=ScoringConfigModel(),
    )
    assert (capped.priority_score or 0) <= 59
    assert any(g["gate"] == "service" and g["applied"] for g in capped.breakdown["gates"])
    assert "no matching Verkies service" in capped.not_qualified_because


@pytest.mark.parametrize(
    ("score", "qualifies", "band"),
    [
        (39.99, True, PriorityBand.REJECT),
        (40, True, PriorityBand.MONITOR),
        (59.99, True, PriorityBand.MONITOR),
        (60, True, PriorityBand.QUALIFIED),
        (74.99, True, PriorityBand.QUALIFIED),
        (75, True, PriorityBand.HIGH),
        (89.99, True, PriorityBand.HIGH),
        (90, True, PriorityBand.HOT),
        (95, False, PriorityBand.QUALIFIED),  # hot/high require qualification
        (80, False, PriorityBand.QUALIFIED),
    ],
)
def test_band_boundaries(score: float, qualifies: bool, band: PriorityBand) -> None:
    assert _band(score, qualifies, ScoringConfigModel()) == band


# --- configuration validation -------------------------------------------------------------


def test_scoring_weights_must_sum_to_one() -> None:
    weights = ScoringConfigModel().weights | {"icp_score": 0.5}
    with pytest.raises(ValidationError, match="sum to 1"):
        ScoringConfigModel(weights=weights)


def test_band_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="ordered"):
        ScoringConfigModel(bands={"hot": 70, "high": 75, "qualified": 60, "monitor": 40})


def test_icp_weights_and_tiers_are_validated() -> None:
    with pytest.raises(ValidationError, match="sum to 1"):
        IcpConfigModel(
            component_weights={
                "need_evidence": 0.5,
                "industry": 0.5,
                "activity": 0.2,
                "geography": 0.1,
            }
        )
    with pytest.raises(ValidationError, match="more than one tier"):
        IcpConfigModel(industry_tiers={"S": ["saas"], "A": ["saas"], "B": []})


def test_changing_weights_changes_priority() -> None:
    facts = facts_from_observations(analyse(*SAAS)[0])
    candidates = detect(facts)
    base = ScoringConfigModel()
    intent_heavy = ScoringConfigModel(
        weights=base.weights | {"intent_score": 0.32, "icp_score": 0.0}
    )
    a = assess(
        facts, candidates, solved_by=solved_by(), icp_config=IcpConfigModel(), scoring_config=base
    )
    b = assess(
        facts,
        candidates,
        solved_by=solved_by(),
        icp_config=IcpConfigModel(),
        scoring_config=intent_heavy,
    )
    assert a.priority_score != b.priority_score


def test_tier_b_needs_stronger_evidence() -> None:
    facts = _facts(("company.industry", {"name": "restaurants"}))
    a = assess(
        facts,
        [_candidate()],
        solved_by=solved_by(),
        icp_config=IcpConfigModel(),
        scoring_config=ScoringConfigModel(),
    )
    industry = next(c for c in a.icp.components if c.name == "industry")
    assert industry.score == 35.0 and "tier B" in industry.note
