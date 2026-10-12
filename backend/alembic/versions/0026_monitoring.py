"""monitoring: watchlists, monitoring alerts, and research runs of kind "monitor" that need no
review (slice 6.1)

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watches",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_watches_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_watches_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watches")),
        sa.UniqueConstraint("account_id", "user_id", name=op.f("uq_watches_account_id_user_id")),
    )
    op.create_index(op.f("ix_watches_account_id"), "watches", ["account_id"], unique=False)
    op.create_index(op.f("ix_watches_user_id"), "watches", ["user_id"], unique=False)
    op.create_table(
        "monitor_alerts",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("research_run_id", sa.UUID(), nullable=False),
        sa.Column("observation_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("signal", sa.String(length=60), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("happened_on", sa.Date(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_monitor_alerts_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["observations.id"],
            name=op.f("fk_monitor_alerts_observation_id_observations"),
        ),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name=op.f("fk_monitor_alerts_research_run_id_research_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"], ["users.id"], name=op.f("fk_monitor_alerts_reviewed_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitor_alerts")),
    )
    op.create_index(
        op.f("ix_monitor_alerts_account_id"), "monitor_alerts", ["account_id"], unique=False
    )
    op.add_column(
        "research_runs",
        sa.Column(
            "kind",
            sa.Enum(
                "research",
                "monitor",
                name="runkind",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
            server_default="research",
        ),
    )
    # A monitoring check is never reviewed.
    op.drop_constraint(op.f("ck_research_runs_reviewstatus"), "research_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_research_runs_reviewstatus"),
        "research_runs",
        "review_status IN ('pending', 'approved', 'rejected', 'not_required')",
    )
    op.create_index(op.f("ix_research_runs_kind"), "research_runs", ["kind"], unique=False)


def downgrade() -> None:
    # Monitoring checks would otherwise turn into research runs waiting for review.
    op.execute("DELETE FROM monitor_alerts")
    op.execute(
        "DELETE FROM observations WHERE research_run_id IN (SELECT id FROM research_runs WHERE kind = 'monitor')"
    )
    op.execute(
        "DELETE FROM evidence WHERE research_run_id IN (SELECT id FROM research_runs WHERE kind = 'monitor')"
    )
    op.execute("DELETE FROM research_runs WHERE kind = 'monitor'")
    op.drop_constraint(op.f("ck_research_runs_reviewstatus"), "research_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_research_runs_reviewstatus"),
        "research_runs",
        "review_status IN ('pending', 'approved', 'rejected')",
    )
    op.drop_index(op.f("ix_research_runs_kind"), table_name="research_runs")
    op.drop_column("research_runs", "kind")
    op.drop_index(op.f("ix_monitor_alerts_account_id"), table_name="monitor_alerts")
    op.drop_table("monitor_alerts")
    op.drop_index(op.f("ix_watches_user_id"), table_name="watches")
    op.drop_index(op.f("ix_watches_account_id"), table_name="watches")
    op.drop_table("watches")
