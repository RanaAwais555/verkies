"""signals: a research stage and an observation area for dated buying signals

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAGES_OLD = ("validate", "crawl", "extract", "detect", "qualify", "score", "match", "brief")
STAGES_NEW = (
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
AREAS_OLD = ("website", "seo", "conversion", "product", "technology", "company", "hiring")
AREAS_NEW = (*AREAS_OLD, "signals")


def _check(table: str, name: str, column: str, values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f(f"ck_{table}_{name}"), table, type_="check")
    listed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(name, table, f"{column} IN ({listed})")


def upgrade() -> None:
    _check("research_stages", "researchstagename", "stage", STAGES_NEW)
    _check("observations", "observationarea", "area", AREAS_NEW)


def downgrade() -> None:
    op.execute("DELETE FROM research_stages WHERE stage = 'signals'")
    _check("research_stages", "researchstagename", "stage", STAGES_OLD)
    # Signal observations are append-only history; downgrading requires removing them first.
    _check("observations", "observationarea", "area", AREAS_OLD)
