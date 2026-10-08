"""default ICP and scoring configuration (version 1)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08

ICP_SPEC.md and SCORING_SPEC.md defaults as a fixed snapshot, so this migration never changes
when code does. Later versions are created through the config API, never by editing this.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ICP_V1 = json.loads("""
{
    "component_weights": {
        "need_evidence": 0.35,
        "industry": 0.3,
        "activity": 0.2,
        "geography": 0.15
    },
    "industry_tiers": {
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
            "product startup"
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
            "education"
        ],
        "B": [
            "construction",
            "automotive",
            "hospitality",
            "restaurants",
            "retail",
            "fitness",
            "beauty",
            "local services"
        ]
    },
    "tier_scores": {
        "S": 100,
        "A": 75,
        "B": 50,
        "other": 20
    },
    "tier_b_evidence_threshold": 50,
    "tier_b_multiplier": 0.7,
    "regions": [
        {
            "priority": 1,
            "name": "United Kingdom",
            "countries": [
                "GB"
            ],
            "score": 100.0,
            "focus_cities": [
                "London",
                "Manchester",
                "Birmingham",
                "Cambridge",
                "Oxford",
                "Bristol",
                "Edinburgh"
            ]
        },
        {
            "priority": 2,
            "name": "United States",
            "countries": [
                "US"
            ],
            "score": 85.0,
            "focus_cities": [
                "New York",
                "San Francisco",
                "Austin",
                "Boston",
                "Seattle",
                "Los Angeles",
                "Chicago",
                "Miami"
            ]
        },
        {
            "priority": 3,
            "name": "Canada",
            "countries": [
                "CA"
            ],
            "score": 70.0,
            "focus_cities": []
        },
        {
            "priority": 4,
            "name": "Australia",
            "countries": [
                "AU"
            ],
            "score": 65.0,
            "focus_cities": []
        },
        {
            "priority": 5,
            "name": "Western Europe",
            "countries": [
                "NL",
                "DE",
                "FR",
                "IE",
                "CH",
                "SE",
                "DK"
            ],
            "score": 55.0,
            "focus_cities": []
        },
        {
            "priority": 6,
            "name": "UAE",
            "countries": [
                "AE"
            ],
            "score": 50.0,
            "focus_cities": [
                "Dubai",
                "Abu Dhabi"
            ]
        }
    ],
    "other_country_score": 20,
    "focus_city_bonus": 5,
    "negative_rules": {
        "parked_domain": {
            "enabled": true,
            "severity": "hard",
            "penalty": 10
        },
        "closed": {
            "enabled": true,
            "severity": "hard",
            "penalty": 10
        },
        "personal_site": {
            "enabled": true,
            "severity": "hard",
            "penalty": 10
        },
        "agency": {
            "enabled": true,
            "severity": "hard",
            "penalty": 10
        },
        "suppressed": {
            "enabled": true,
            "severity": "hard",
            "penalty": 10
        },
        "duplicate": {
            "enabled": true,
            "severity": "review",
            "penalty": 10
        },
        "no_commercial_opportunity": {
            "enabled": true,
            "severity": "soft",
            "penalty": 15.0
        },
        "no_relevant_service": {
            "enabled": true,
            "severity": "soft",
            "penalty": 10.0
        },
        "insufficient_evidence": {
            "enabled": true,
            "severity": "soft",
            "penalty": 10.0
        },
        "no_reachable_buyer": {
            "enabled": true,
            "severity": "soft",
            "penalty": 5.0
        },
        "irrelevant_industry": {
            "enabled": true,
            "severity": "soft",
            "penalty": 15.0
        },
        "existing_solution_sufficient": {
            "enabled": true,
            "severity": "soft",
            "penalty": 10.0
        }
    },
    "min_opportunity_confidence": 0.5,
    "insufficient_evidence_below": 30,
    "no_buyer_below": 25
}
""")

SCORING_V1 = json.loads("""
{
    "weights": {
        "icp_score": 0.2,
        "opportunity_score": 0.2,
        "intent_score": 0.12,
        "service_fit": 0.1,
        "buyer_confidence": 0.08,
        "data_confidence": 0.08,
        "commercial_potential": 0.08,
        "timing_score": 0.06,
        "client_similarity": 0.04,
        "evidence_strength": 0.04
    },
    "bands": {
        "hot": 90,
        "high": 75,
        "qualified": 60,
        "monitor": 40
    },
    "gates": {
        "hard_reject_cap": 39,
        "min_coverage": 0.5,
        "low_coverage_cap": 59,
        "min_evidence_strength": 30,
        "low_evidence_cap": 59,
        "no_service_cap": 59,
        "min_data_confidence": 40,
        "low_data_cap": 74
    },
    "qualification": {
        "min_icp": 50,
        "min_evidence_strength": 30,
        "min_data_confidence": 40,
        "min_problem_signals": 2
    }
}
""")


def upgrade() -> None:
    conn = op.get_bind()
    for table, config in (("icp_configs", ICP_V1), ("scoring_configs", SCORING_V1)):
        conn.execute(
            sa.text(
                f"INSERT INTO {table} (id, version, is_active, config, note) "  # noqa: S608
                "VALUES (gen_random_uuid(), 1, true, CAST(:c AS jsonb), :n)"
            ),
            {"c": json.dumps(config), "n": "Defaults from the specification"},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM icp_configs WHERE version = 1"))
    conn.execute(sa.text("DELETE FROM scoring_configs WHERE version = 1"))
