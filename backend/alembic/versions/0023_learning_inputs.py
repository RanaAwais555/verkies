"""learning inputs: salesperson feedback and what was true when each deal was won or lost
(slice 5.1)

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-12

Deals already closed get their outcome from `python -m app.cli backfill-outcomes`, marked as
captured late.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sales_feedback",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("opportunity_id", sa.UUID(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "good_lead",
                "bad_lead",
                "contacted",
                "meeting_booked",
                "proposal_sent",
                "won",
                "lost",
                "wrong_buyer",
                "wrong_service",
                "not_now",
                "not_icp",
                "duplicate",
                "competitor",
                "opportunity_confirmed",
                "opportunity_incorrect",
                name="feedbackkind",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("given_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_sales_feedback_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["given_by_id"], ["users.id"], name=op.f("fk_sales_feedback_given_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], name=op.f("fk_sales_feedback_lead_id_leads")
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_sales_feedback_opportunity_id_opportunities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales_feedback")),
    )
    op.create_index(
        op.f("ix_sales_feedback_account_id"), "sales_feedback", ["account_id"], unique=False
    )
    op.create_index(op.f("ix_sales_feedback_kind"), "sales_feedback", ["kind"], unique=False)
    op.create_table(
        "deal_outcomes",
        sa.Column("deal_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "open",
                "won",
                "lost",
                "nurture",
                "inactive",
                name="stageoutcome",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "lost_reason",
            sa.Enum(
                "price",
                "no_budget",
                "timing",
                "competitor",
                "internal_development",
                "freelancer",
                "another_agency",
                "cancelled",
                "no_decision",
                "lost_contact",
                "requirements_changed",
                "poor_fit",
                "other",
                name="lostreason",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=True,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_late", sa.Boolean(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pipeline_key", sa.String(length=60), nullable=False),
        sa.Column("value", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=True),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("company_size_band", sa.String(length=40), nullable=True),
        sa.Column("hq_country", sa.String(length=2), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=True),
        sa.Column("buyer_role", sa.String(length=40), nullable=True),
        sa.Column("deal_days", sa.Integer(), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=True),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("close_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reference_project_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_deal_outcomes_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["opportunity_categories.id"],
            name=op.f("fk_deal_outcomes_category_id_opportunity_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["deal_id"], ["deals.id"], name=op.f("fk_deal_outcomes_deal_id_deals")
        ),
        sa.ForeignKeyConstraint(
            ["reference_project_id"],
            ["reference_projects.id"],
            name=op.f("fk_deal_outcomes_reference_project_id_reference_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["services.id"], name=op.f("fk_deal_outcomes_service_id_services")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deal_outcomes")),
    )
    op.create_index(
        op.f("ix_deal_outcomes_account_id"), "deal_outcomes", ["account_id"], unique=False
    )
    op.create_index(op.f("ix_deal_outcomes_deal_id"), "deal_outcomes", ["deal_id"], unique=False)
    op.create_index(
        "uq_deal_outcomes_current",
        "deal_outcomes",
        ["deal_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_deal_outcomes_current",
        table_name="deal_outcomes",
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.drop_index(op.f("ix_deal_outcomes_deal_id"), table_name="deal_outcomes")
    op.drop_index(op.f("ix_deal_outcomes_account_id"), table_name="deal_outcomes")
    op.drop_table("deal_outcomes")
    op.drop_index(op.f("ix_sales_feedback_kind"), table_name="sales_feedback")
    op.drop_index(op.f("ix_sales_feedback_account_id"), table_name="sales_feedback")
    op.drop_table("sales_feedback")
