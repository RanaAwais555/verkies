"""ICP configuration (ICP_SPEC.md). Stored versioned in icp_configs; these are the defaults.

Industry and geography never qualify a lead on their own: they are two of four weighted
components, and need evidence carries the most weight.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

WEIGHT_TOLERANCE = 1e-6


class Region(BaseModel):
    priority: int
    name: str
    countries: list[str]  # ISO 3166-1 alpha-2
    score: float = Field(ge=0, le=100)
    focus_cities: list[str] = Field(default_factory=list)


class NegativeRule(BaseModel):
    enabled: bool = True
    severity: Literal["hard", "soft", "review"]
    penalty: float = Field(default=10, ge=0, le=100)  # soft rules: points off ICP fit


class IcpConfigModel(BaseModel):
    component_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "need_evidence": 0.35,
            "industry": 0.30,
            "activity": 0.20,
            "geography": 0.15,
        }
    )
    industry_tiers: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "S": [
                "saas",
                "ai",
                "fintech",
                "healthtech",
                "proptech",
                "edtech",
                "martech",
                "marketplace",
                "software company",
                "funded startup",
                "product startup",
            ],
            "A": [
                "immigration",
                "legal",
                "recruitment",
                "accounting",
                "consulting",
                "healthcare",
                "logistics",
                "travel technology",
                "real estate",
                "professional services",
                "e-commerce",
                "education",
            ],
            "B": [
                "construction",
                "automotive",
                "hospitality",
                "restaurants",
                "retail",
                "fitness",
                "beauty",
                "local services",
            ],
        }
    )
    tier_scores: dict[str, float] = Field(
        default_factory=lambda: {"S": 100.0, "A": 75.0, "B": 50.0, "other": 20.0}
    )
    # Tier B needs stronger evidence (ICP_SPEC.md §2).
    tier_b_evidence_threshold: float = 50
    tier_b_multiplier: float = Field(default=0.7, ge=0, le=1)
    regions: list[Region] = Field(
        default_factory=lambda: [
            Region(
                priority=1,
                name="United Kingdom",
                countries=["GB"],
                score=100,
                focus_cities=[
                    "London",
                    "Manchester",
                    "Birmingham",
                    "Cambridge",
                    "Oxford",
                    "Bristol",
                    "Edinburgh",
                ],
            ),
            Region(
                priority=2,
                name="United States",
                countries=["US"],
                score=85,
                focus_cities=[
                    "New York",
                    "San Francisco",
                    "Austin",
                    "Boston",
                    "Seattle",
                    "Los Angeles",
                    "Chicago",
                    "Miami",
                ],
            ),
            Region(priority=3, name="Canada", countries=["CA"], score=70),
            Region(priority=4, name="Australia", countries=["AU"], score=65),
            Region(
                priority=5,
                name="Western Europe",
                countries=["NL", "DE", "FR", "IE", "CH", "SE", "DK"],
                score=55,
            ),
            Region(
                priority=6,
                name="UAE",
                countries=["AE"],
                score=50,
                focus_cities=["Dubai", "Abu Dhabi"],
            ),
        ]
    )
    other_country_score: float = 20
    focus_city_bonus: float = 5
    negative_rules: dict[str, NegativeRule] = Field(
        default_factory=lambda: {
            "parked_domain": NegativeRule(severity="hard"),
            "closed": NegativeRule(severity="hard"),
            "personal_site": NegativeRule(severity="hard"),
            "agency": NegativeRule(severity="hard"),
            "suppressed": NegativeRule(severity="hard"),
            "duplicate": NegativeRule(severity="review"),
            "no_commercial_opportunity": NegativeRule(severity="soft", penalty=15),
            "no_relevant_service": NegativeRule(severity="soft", penalty=10),
            "insufficient_evidence": NegativeRule(severity="soft", penalty=10),
            "no_reachable_buyer": NegativeRule(severity="soft", penalty=5),
            "irrelevant_industry": NegativeRule(severity="soft", penalty=15),
            "existing_solution_sufficient": NegativeRule(severity="soft", penalty=10),
        }
    )
    min_opportunity_confidence: float = Field(default=0.5, ge=0, le=1)
    insufficient_evidence_below: float = 30
    no_buyer_below: float = 25

    @model_validator(mode="after")
    def _check(self) -> "IcpConfigModel":
        expected = {"need_evidence", "industry", "activity", "geography"}
        if set(self.component_weights) != expected:
            raise ValueError(f"component_weights must have exactly {sorted(expected)}")
        if abs(sum(self.component_weights.values()) - 1) > WEIGHT_TOLERANCE:
            raise ValueError("component_weights must sum to 1")
        seen: set[str] = set()
        for tier, names in self.industry_tiers.items():
            if tier not in self.tier_scores:
                raise ValueError(f"tier {tier} has no score")
            for name in names:
                if name in seen:
                    raise ValueError(f"industry {name} is in more than one tier")
                seen.add(name)
        return self

    def tier_of(self, industry: str) -> str | None:
        for tier, names in self.industry_tiers.items():
            if industry in names:
                return tier
        return None
