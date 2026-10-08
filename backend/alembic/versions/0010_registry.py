"""registry: an enrich stage and an observation area for official company registries

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAGES_OLD = (
    "validate",
    "crawl",
    "extract",
    "signals",
    "detect",
    "qualify",
    "score",
    "match",
    "brief",
)
STAGES_NEW = (
    "validate",
    "crawl",
    "extract",
    "signals",
    "enrich",
    "detect",
    "qualify",
    "score",
    "match",
    "brief",
)
AREAS_OLD = (
    "website",
    "seo",
    "conversion",
    "product",
    "technology",
    "company",
    "hiring",
    "signals",
)
AREAS_NEW = (*AREAS_OLD, "registry")


def _check(table: str, name: str, column: str, values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f(f"ck_{table}_{name}"), table, type_="check")
    listed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(name, table, f"{column} IN ({listed})")


def upgrade() -> None:
    _check("research_stages", "researchstagename", "stage", STAGES_NEW)
    _check("observations", "observationarea", "area", AREAS_NEW)


def downgrade() -> None:
    op.execute("DELETE FROM research_stages WHERE stage = 'enrich'")
    _check("research_stages", "researchstagename", "stage", STAGES_OLD)
    _check("observations", "observationarea", "area", AREAS_OLD)
