"""account merge: merged accounts point at the account they were merged into, reviewers can
mark a suggested pair as not duplicates, and merging needs its own permission (slice 2.6)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-11

Evidence, claims, observations, score snapshots and timeline events are append-only (0002), so a
merge cannot move them. The merged account keeps them and points at the survivor through
`merged_into_id`; the survivor's reads include its merged accounts.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = ("accounts.merge", "Review possible duplicate accounts and merge them")
GRANTED_TO = ("admin", "founder", "sales_manager")


def upgrade() -> None:
    op.add_column(
        "accounts", sa.Column("merged_into_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_accounts_merged_into_id_accounts"),
        "accounts",
        "accounts",
        ["merged_into_id"],
        ["id"],
    )
    op.create_index(op.f("ix_accounts_merged_into_id"), "accounts", ["merged_into_id"])

    op.create_table(
        "account_duplicate_dismissals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dismissed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # One row per pair, stored with the smaller id first.
        sa.CheckConstraint(
            "account_a_id < account_b_id", name=op.f("ck_account_duplicate_dismissals_ordered_pair")
        ),
        sa.ForeignKeyConstraint(
            ["account_a_id"],
            ["accounts.id"],
            name=op.f("fk_account_duplicate_dismissals_account_a_id_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["account_b_id"],
            ["accounts.id"],
            name=op.f("fk_account_duplicate_dismissals_account_b_id_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["dismissed_by_id"],
            ["users.id"],
            name=op.f("fk_account_duplicate_dismissals_dismissed_by_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_duplicate_dismissals")),
        sa.UniqueConstraint(
            "account_a_id",
            "account_b_id",
            name=op.f("uq_account_duplicate_dismissals_account_a_id_account_b_id"),
        ),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO permissions (id, key, description) VALUES (gen_random_uuid(), :k, :d)"
        ),
        {"k": PERMISSION[0], "d": PERMISSION[1]},
    )
    conn.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r, permissions p WHERE r.key = ANY(:roles) AND p.key = :k"
        ),
        {"roles": list(GRANTED_TO), "k": PERMISSION[0]},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE key = :k)"
        ),
        {"k": PERMISSION[0]},
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE key = :k"), {"k": PERMISSION[0]})
    op.drop_table("account_duplicate_dismissals")
    op.drop_index(op.f("ix_accounts_merged_into_id"), table_name="accounts")
    op.drop_constraint(op.f("fk_accounts_merged_into_id_accounts"), "accounts", type_="foreignkey")
    op.drop_column("accounts", "merged_into_id")
