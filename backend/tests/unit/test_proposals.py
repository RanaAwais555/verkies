"""Slice 5.3: the arithmetic of learned proposals."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.enums import StageOutcome
from app.core.errors import ValidationFailed
from app.learning.models import DealOutcome
from app.learning.proposals import (
    MAX_STEP,
    _round_weights,
    correlation,
    draft_icp,
    draft_scoring,
)
from app.qualification.config import IcpConfigModel
from app.scoring.config import ScoringConfigModel

SCORING = ScoringConfigModel().model_dump()
ICP = IcpConfigModel().model_dump()


def outcome(won: bool, industry: str | None = "legal", **scores: float) -> DealOutcome:
    return DealOutcome(
        id=uuid.uuid4(),
        outcome=StageOutcome.WON if won else StageOutcome.LOST,
        industry=industry,
        first_scores=scores or None,
        closed_at=datetime.now(UTC),
    )


def test_correlation() -> None:
    assert correlation([(90, True), (80, True), (30, False), (20, False)]) == pytest.approx(
        0.99, abs=0.01
    )
    assert correlation([(50, True), (50, False)]) == 0  # no spread, no signal
    assert correlation([(10, True), (90, True)]) == 0  # everyone won


def test_rounded_weights_always_sum_to_one() -> None:
    weights = _round_weights({"a": 1, "b": 1, "c": 1})
    assert sum(weights.values()) == pytest.approx(1) and sorted(weights.values()) == [
        0.33,
        0.33,
        0.34,
    ]


def test_rounding_never_takes_a_raised_weight_back() -> None:
    # A real case: ICP fit raised to 0.25 of 1.0416 (24%); rounding the rest must not eat that.
    raw = {"icp": 0.25, "opp": 0.1916, "a": 0.12, "b": 0.10, "c": 0.08, "d": 0.08, "e": 0.08}
    raw |= {"f": 0.06, "g": 0.04, "h": 0.04}
    weights = _round_weights(raw)
    assert weights["icp"] == 0.24 and sum(weights.values()) == pytest.approx(1)


def test_nothing_is_proposed_from_too_few_deals() -> None:
    few = [outcome(True, icp_score=80)] * 4 + [outcome(False, icp_score=20)] * 5
    with pytest.raises(ValidationFailed) as refused:
        draft_scoring(few, SCORING, 1, 5)
    assert refused.value.code == "not_enough_outcomes"


def test_a_dimension_that_separates_wins_gains_weight_within_the_cap() -> None:
    deals = [outcome(True, icp_score=80 + i) for i in range(5)] + [
        outcome(False, icp_score=30 + i) for i in range(5)
    ]
    found = draft_scoring(deals, SCORING, 1, 5)
    weights: dict[str, Any] = found.config["weights"]
    assert sum(weights.values()) == pytest.approx(1)
    assert weights["icp_score"] > SCORING["weights"]["icp_score"]
    # The cap holds before renormalising: icp can grow by at most a quarter of itself.
    assert weights["icp_score"] <= round(0.2 * (1 + MAX_STEP) / (1 + 0.2 * MAX_STEP), 2) + 0.01
    icp = next(c for c in found.changes if c["key"] == "icp_score")
    assert icp["won_mean"] == 82 and icp["lost_mean"] == 32 and icp["known_won"] == 5
    # Dimensions nobody knew keep their share; only the renormalisation moves them.
    assert all(c["r"] is None for c in found.changes if c["key"] != "icp_score")
    assert found.basis["won"] == 5 and found.basis["config_version"] == 1


def test_the_same_outcomes_give_the_same_proposal() -> None:
    deals = [outcome(True, icp_score=70 + i) for i in range(6)] + [
        outcome(False, icp_score=40 + i) for i in range(6)
    ]
    first = draft_scoring(deals, SCORING, 3, 5)
    again = draft_scoring(list(reversed(deals)), SCORING, 3, 5)
    assert first.config == again.config and first.basis == again.basis


def test_icp_tiers_move_one_step_on_a_clear_difference() -> None:
    deals = (
        [outcome(True, "legal")] * 5
        + [outcome(False, "retail")] * 5
        + [outcome(True, "logistics")] * 2
        + [outcome(False, "logistics")] * 2
    )
    found = draft_icp(deals, ICP, 1, 5)
    moved = {c["key"]: (c["from"], c["to"]) for c in found.changes}
    assert moved == {"legal": ("A", "S"), "retail": ("B", "other")}  # logistics: too few deals
    tiers = found.config["industry_tiers"]
    assert "legal" in tiers["S"] and "legal" not in tiers["A"]
    assert all("retail" not in names for names in tiers.values())
    IcpConfigModel.model_validate(found.config)  # still a valid configuration
