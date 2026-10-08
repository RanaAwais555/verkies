"""registry discovery: Companies House search jobs, and rows that are still finding (or did
not find) a website

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_OLD = ("csv_import", "search")
KINDS_NEW = (*KINDS_OLD, "registry")
JOB_STATUS_OLD = ("uploaded", "checked")
JOB_STATUS_NEW = (*JOB_STATUS_OLD, "running")
ROW_STATUS_OLD = (
    "pending",
    "new",
    "invalid",
    "duplicate_in_file",
    "existing_account",
    "possible_duplicate",
    "already_researched",
    "suppressed",
    "queued",
)
ROW_STATUS_NEW = (*ROW_STATUS_OLD, "finding_website", "no_website")


def _check(table: str, name: str, column: str, values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f(f"ck_{table}_{name}"), table, type_="check")
    listed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(name, table, f"{column} IN ({listed})")


def upgrade() -> None:
    _check("discovery_jobs", "discoverykind", "kind", KINDS_NEW)
    _check("discovery_jobs", "discoverystatus", "status", JOB_STATUS_NEW)
    _check("discovered_companies", "candidatestatus", "status", ROW_STATUS_NEW)


def downgrade() -> None:
    op.execute("DELETE FROM discovery_jobs WHERE kind = 'registry'")
    _check("discovered_companies", "candidatestatus", "status", ROW_STATUS_OLD)
    _check("discovery_jobs", "discoverystatus", "status", JOB_STATUS_OLD)
    _check("discovery_jobs", "discoverykind", "kind", KINDS_OLD)
