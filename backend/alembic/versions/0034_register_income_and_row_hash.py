"""register income and row hash: a charity's latest income, and each record's content hash so a
refresh rewrites only what changed (slice 8.3)

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("register_records", sa.Column("income", sa.BigInteger(), nullable=True))
    op.add_column("register_records", sa.Column("row_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("register_records", "row_hash")
    op.drop_column("register_records", "income")
