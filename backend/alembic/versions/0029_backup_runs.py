"""backup runs: each step the backup service took (dump, documents, off-site copy, restore
drill) and how it went (slice 7.2)

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("bytes", sa.BigInteger(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('dump', 'documents', 'offsite', 'drill')", name=op.f("ck_backup_runs_kind")
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'failed', 'skipped')", name=op.f("ck_backup_runs_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backup_runs")),
    )
    op.create_index(op.f("ix_backup_runs_kind"), "backup_runs", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_backup_runs_kind"), table_name="backup_runs")
    op.drop_table("backup_runs")
