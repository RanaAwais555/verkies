"""learned proposals: scoring and ICP changes worked out from deal outcomes, never active until a
person activates them (slice 5.3)

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learned_proposals",
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "proposed",
                "activated",
                "dismissed",
                "superseded",
                name="proposalstatus",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("based_on_version", sa.Integer(), nullable=False),
        sa.Column("proposed_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("basis", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("decided_by_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("activated_version", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_learned_proposals_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"], ["users.id"], name=op.f("fk_learned_proposals_decided_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learned_proposals")),
    )
    op.create_index(
        op.f("ix_learned_proposals_status"), "learned_proposals", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_learned_proposals_status"), table_name="learned_proposals")
    op.drop_table("learned_proposals")
