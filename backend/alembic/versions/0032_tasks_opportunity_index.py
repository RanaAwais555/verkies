"""index tasks.opportunity_id: the follow-up engine reads each opportunity's latest completed task
(slice 7.5)

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-13

Without it, finding stale opportunities scanned every task once per opportunity: with 20,000
accounts the follow-up list took over five minutes; with it, well under a second.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(op.f("ix_tasks_opportunity_id"), "tasks", ["opportunity_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_opportunity_id"), table_name="tasks")
