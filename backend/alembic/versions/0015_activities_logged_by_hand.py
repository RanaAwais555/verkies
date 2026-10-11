"""activities logged by hand: calls, meetings, notes and messages against a deal as well as an
account, contact or opportunity, with who spoke, so relationship tracking and the follow-up engine
can read them (slice 3.2)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-11

Nothing wrote activities before this slice; any row that exists is treated as an internal note,
which counts towards neither attempts nor replies.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("deal_id", sa.UUID(), nullable=True))
    op.add_column(
        "activities",
        sa.Column(
            "direction",
            sa.Enum(
                "outbound",
                "inbound",
                "conversation",
                "internal",
                name="activitydirection",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
            server_default="internal",
        ),
    )
    op.alter_column("activities", "direction", server_default=None)
    op.create_index(
        "ix_activities_account_time", "activities", ["account_id", "occurred_at"], unique=False
    )
    op.create_index(
        "ix_activities_contact_time", "activities", ["contact_id", "occurred_at"], unique=False
    )
    op.create_index(op.f("ix_activities_deal_id"), "activities", ["deal_id"], unique=False)
    op.create_index(
        op.f("ix_activities_opportunity_id"), "activities", ["opportunity_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_activities_deal_id_deals"), "activities", "deals", ["deal_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_activities_deal_id_deals"), "activities", type_="foreignkey")
    op.drop_index(op.f("ix_activities_opportunity_id"), table_name="activities")
    op.drop_index(op.f("ix_activities_deal_id"), table_name="activities")
    op.drop_index("ix_activities_contact_time", table_name="activities")
    op.drop_index("ix_activities_account_time", table_name="activities")
    op.drop_column("activities", "direction")
    op.drop_column("activities", "deal_id")
