"""approval: one lead per research run, and indexes for the review queue and the CRM views

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Approving the same run twice must be impossible even if two reviewers click at once.
    op.create_index(
        "uq_leads_research_run",
        "leads",
        ["research_run_id"],
        unique=True,
        postgresql_where=sa.text("research_run_id IS NOT NULL"),
    )
    op.create_index("ix_opportunities_lead_id", "opportunities", ["lead_id"])
    op.create_index("ix_research_runs_status_review", "research_runs", ["status", "review_status"])


def downgrade() -> None:
    op.drop_index("ix_research_runs_status_review", table_name="research_runs")
    op.drop_index("ix_opportunities_lead_id", table_name="opportunities")
    op.drop_index("uq_leads_research_run", table_name="leads")
