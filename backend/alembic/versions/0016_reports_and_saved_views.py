"""reports and saved views: the `reports.team` permission for the management dashboard, and saved
views with the team's starting set (master context §13, slice 3.3)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-11

A saved view stores a page and its query string, nothing else, so it always shows current data
through that page's own permissions. The views for clients (expansion, at risk) arrive with
Phase 4, when there are clients to show.
"""

from collections.abc import Sequence
from urllib.parse import urlencode

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = ("reports.team", "See the management dashboard: every salesperson's numbers")
GRANTED_TO = ("admin", "founder", "sales_manager")

# (name, path, query) shared with the team, in this order.
TEAM_VIEWS: list[tuple[str, str, dict[str, str]]] = [
    ("My Hot Leads", "/leads", {"q": "my hot leads"}),
    ("Follow-ups Today", "/tasks", {"due": "today"}),
    ("Stale Opportunities", "/follow-ups", {"kind": "stale_opportunity"}),
    ("UK SaaS Prospects", "/leads", {"q": "SaaS prospects in the UK"}),
    ("High Value Pipeline", "/pipeline", {"min_value": "10000"}),
    ("New Buying Signals", "/leads", {"q": "buying signals in the last 30 days"}),
    ("Unassigned Leads", "/leads", {"q": "unassigned leads"}),
    ("Deals Closing This Month", "/pipeline", {"closing": "this_month"}),
]


def upgrade() -> None:
    op.create_table(
        "saved_views",
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("path", sa.String(length=200), nullable=False),
        sa.Column("query", sa.String(length=1000), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("path LIKE '/%%'", name=op.f("ck_saved_views_path_is_local")),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_saved_views_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_saved_views_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_views")),
    )
    op.create_index(op.f("ix_saved_views_user_id"), "saved_views", ["user_id"], unique=False)

    conn = op.get_bind()
    for position, (name, path, query) in enumerate(TEAM_VIEWS):
        conn.execute(
            sa.text(
                "INSERT INTO saved_views (id, user_id, name, path, query, position)"
                " VALUES (gen_random_uuid(), NULL, :n, :p, :q, :pos)"
            ),
            {"n": name, "p": path, "q": urlencode(query), "pos": position},
        )
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
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE key = :k)"
        ),
        {"k": PERMISSION[0]},
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE key = :k"), {"k": PERMISSION[0]})
    op.drop_index(op.f("ix_saved_views_user_id"), table_name="saved_views")
    op.drop_table("saved_views")
