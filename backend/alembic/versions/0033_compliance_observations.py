"""compliance observations: what a site must show by law or its regulator (slice 8.2)

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AREAS_OLD = (
    "website",
    "seo",
    "conversion",
    "product",
    "technology",
    "company",
    "hiring",
    "signals",
    "registry",
)
AREAS_NEW = (*AREAS_OLD, "compliance")


def _check(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_observations_observationarea"), "observations", type_="check")
    listed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint("observationarea", "observations", f"area IN ({listed})")


def upgrade() -> None:
    _check(AREAS_NEW)


def downgrade() -> None:
    op.execute("DELETE FROM observations WHERE area = 'compliance'")
    _check(AREAS_OLD)
