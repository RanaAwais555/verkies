"""client similarity: a similarity result can be against a won client as well as a reference
project, exactly one of the two (slice 5.4)

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("similarity_results", sa.Column("client_account_id", sa.UUID(), nullable=True))
    op.alter_column(
        "similarity_results", "reference_project_id", existing_type=sa.UUID(), nullable=True
    )
    op.create_unique_constraint(
        op.f("uq_similarity_results_research_run_id_client_account_id"),
        "similarity_results",
        ["research_run_id", "client_account_id"],
    )
    op.create_foreign_key(
        op.f("fk_similarity_results_client_account_id_accounts"),
        "similarity_results",
        "accounts",
        ["client_account_id"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_similarity_results_one_reference"),
        "similarity_results",
        "(reference_project_id IS NULL) <> (client_account_id IS NULL)",
    )


def downgrade() -> None:
    # Results against clients have nowhere to go without the column.
    op.execute("DELETE FROM similarity_results WHERE client_account_id IS NOT NULL")
    op.drop_constraint(
        op.f("ck_similarity_results_one_reference"), "similarity_results", type_="check"
    )
    op.drop_constraint(
        op.f("fk_similarity_results_client_account_id_accounts"),
        "similarity_results",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("uq_similarity_results_research_run_id_client_account_id"),
        "similarity_results",
        type_="unique",
    )
    op.alter_column(
        "similarity_results", "reference_project_id", existing_type=sa.UUID(), nullable=False
    )
    op.drop_column("similarity_results", "client_account_id")
