"""Scoring configuration (SCORING_SPEC.md). Stored versioned in scoring_configs; these are
the defaults. Nothing here is hard-coded in the engine."""

from pydantic import BaseModel, Field, model_validator

DIMENSIONS = (
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
WEIGHT_TOLERANCE = 1e-6


class Bands(BaseModel):
    hot: float = 90
    high: float = 75
    qualified: float = 60
    monitor: float = 40


class Gates(BaseModel):
    hard_reject_cap: float = 39
    min_coverage: float = Field(default=0.5, ge=0, le=1)
    low_coverage_cap: float = 59
    min_evidence_strength: float = 30
    low_evidence_cap: float = 59
    no_service_cap: float = 59
    min_data_confidence: float = 40
    low_data_cap: float = 74


class Qualification(BaseModel):
    min_icp: float = 50
    min_evidence_strength: float = 30
    min_data_confidence: float = 40
    min_problem_signals: int = 2


class ScoringConfigModel(BaseModel):
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "icp_score": 0.20,
            "opportunity_score": 0.20,
            "intent_score": 0.12,
            "service_fit": 0.10,
            "buyer_confidence": 0.08,
            "data_confidence": 0.08,
            "commercial_potential": 0.08,
            "timing_score": 0.06,
            "client_similarity": 0.04,
            "evidence_strength": 0.04,
        }
    )
    bands: Bands = Field(default_factory=Bands)
    gates: Gates = Field(default_factory=Gates)
    qualification: Qualification = Field(default_factory=Qualification)

    @model_validator(mode="after")
    def _check(self) -> "ScoringConfigModel":
        if set(self.weights) != set(DIMENSIONS):
            raise ValueError(f"weights must cover exactly {list(DIMENSIONS)}")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("weights cannot be negative")
        if abs(sum(self.weights.values()) - 1) > WEIGHT_TOLERANCE:
            raise ValueError("weights must sum to 1")
        b = self.bands
        if not (100 >= b.hot > b.high > b.qualified > b.monitor > 0):
            raise ValueError(
                "band thresholds must be ordered: 100 >= hot > high > qualified > monitor > 0"
            )
        return self
