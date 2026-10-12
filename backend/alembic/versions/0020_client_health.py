"""client health: client feedback, the history of each client's health colour, and the team's
"At-Risk Clients" saved view (slice 4.2)

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-12

Health itself is computed from the records on every read; the snapshots are only its history.
"""

from collections.abc import Sequence
from urllib.parse import urlencode

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# After the eight team views of migration 0016.
CLIENT_VIEWS: list[tuple[str, str, dict[str, str]]] = [
    ("At-Risk Clients", "/clients", {"health": "red"}),
]
FIRST_POSITION = 8


def upgrade() -> None:
    op.create_table(
        "client_health_snapshots",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column(
            "colour",
            sa.Enum(
                "green",
                "yellow",
                "red",
                name="healthcolour",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "assessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_client_health_snapshots_account_id_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_health_snapshots")),
    )
    op.create_index(
        op.f("ix_client_health_snapshots_account_id"),
        "client_health_snapshots",
        ["account_id"],
        unique=False,
    )
    op.create_table(
        "client_feedback",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column(
            "sentiment",
            sa.Enum(
                "positive",
                "neutral",
                "negative",
                name="sentiment",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_client_feedback_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_client_feedback_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_id"], ["users.id"], name=op.f("fk_client_feedback_recorded_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_feedback")),
    )
    op.create_index(
        op.f("ix_client_feedback_account_id"), "client_feedback", ["account_id"], unique=False
    )
    seed_client_views(op.get_bind())


def seed_client_views(conn: sa.Connection) -> None:
    for offset, (name, path, query) in enumerate(CLIENT_VIEWS):
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
        {"n": [name for name, _, _ in CLIENT_VIEWS]},
    )
    op.drop_index(op.f("ix_client_feedback_account_id"), table_name="client_feedback")
    op.drop_table("client_feedback")
    op.drop_index(
        op.f("ix_client_health_snapshots_account_id"), table_name="client_health_snapshots"
    )
    op.drop_table("client_health_snapshots")
