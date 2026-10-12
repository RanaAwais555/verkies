"""expansion and referrals: decisions on expansion suggestions, referrals, and the team's
"Clients With Expansion Opportunities" saved view (slice 4.3)

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-12

Expansion suggestions are computed from evidence-backed research findings; only decisions are
stored. A referral's conversion and revenue are read from deals, never stored.
"""

from collections.abc import Sequence
from urllib.parse import urlencode

import sqlalchemy as sa

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# After the views of migrations 0016 and 0020.
EXPANSION_VIEWS: list[tuple[str, str, dict[str, str]]] = [
    ("Clients With Expansion Opportunities", "/clients", {"expansion": "1"}),
]
FIRST_POSITION = 9


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("referrer_account_id", sa.UUID(), nullable=True),
        sa.Column("referrer_contact_id", sa.UUID(), nullable=True),
        sa.Column("referrer_name", sa.String(length=200), nullable=False),
        sa.Column("relationship", sa.String(length=120), nullable=True),
        sa.Column("referred_company", sa.String(length=300), nullable=False),
        sa.Column("referred_domain", sa.String(length=253), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "received",
                "contacted",
                "declined",
                name="referralstatus",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_id"], ["users.id"], name=op.f("fk_referrals_recorded_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["referrer_account_id"],
            ["accounts.id"],
            name=op.f("fk_referrals_referrer_account_id_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["referrer_contact_id"],
            ["contacts.id"],
            name=op.f("fk_referrals_referrer_contact_id_contacts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_referrals")),
    )
    op.create_index(
        op.f("ix_referrals_referred_domain"), "referrals", ["referred_domain"], unique=False
    )
    op.create_index(
        op.f("ix_referrals_referrer_account_id"), "referrals", ["referrer_account_id"], unique=False
    )
    op.create_table(
        "expansion_opportunities",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=True),
        sa.Column(
            "decision",
            sa.Enum(
                "opened",
                "dismissed",
                name="expansiondecision",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("opportunity_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_expansion_opportunities_account_id_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["opportunity_candidates.id"],
            name=op.f("fk_expansion_opportunities_candidate_id_opportunity_candidates"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["opportunity_categories.id"],
            name=op.f("fk_expansion_opportunities_category_id_opportunity_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["users.id"],
            name=op.f("fk_expansion_opportunities_decided_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_expansion_opportunities_opportunity_id_opportunities"),
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name=op.f("fk_expansion_opportunities_service_id_services"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expansion_opportunities")),
        sa.UniqueConstraint(
            "account_id",
            "category_id",
            name=op.f("uq_expansion_opportunities_account_id_category_id"),
        ),
    )
    op.create_index(
        op.f("ix_expansion_opportunities_account_id"),
        "expansion_opportunities",
        ["account_id"],
        unique=False,
    )

    seed_expansion_views(op.get_bind())


def seed_expansion_views(conn: sa.Connection) -> None:
    for offset, (name, path, query) in enumerate(EXPANSION_VIEWS):
        conn.execute(
            sa.text(
                "INSERT INTO saved_views (id, user_id, name, path, query, position)"
                " VALUES (gen_random_uuid(), NULL, :n, :p, :q, :pos)"
            ),
            {"n": name, "p": path, "q": urlencode(query), "pos": FIRST_POSITION + offset},
        )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM saved_views WHERE user_id IS NULL AND name = ANY(:n)"),
        {"n": [name for name, _, _ in EXPANSION_VIEWS]},
    )
    op.drop_index(
        op.f("ix_expansion_opportunities_account_id"), table_name="expansion_opportunities"
    )
    op.drop_table("expansion_opportunities")
    op.drop_index(op.f("ix_referrals_referrer_account_id"), table_name="referrals")
    op.drop_index(op.f("ix_referrals_referred_domain"), table_name="referrals")
    op.drop_table("referrals")
