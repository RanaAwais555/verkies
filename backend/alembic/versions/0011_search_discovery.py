"""search discovery: discovery jobs can come from a web search

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _kinds(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_discovery_jobs_discoverykind"), "discovery_jobs", type_="check")
    listed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint("discoverykind", "discovery_jobs", f"kind IN ({listed})")


def upgrade() -> None:
    _kinds(("csv_import", "search"))


def downgrade() -> None:
    op.execute("DELETE FROM discovery_jobs WHERE kind = 'search'")
    _kinds(("csv_import",))
