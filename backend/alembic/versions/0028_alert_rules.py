"""alert rules and notifications: rules that flag monitoring alerts or create follow-up tasks,
in-app notifications, and which kinds each person has switched off (slice 6.3)

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-13
"""

import json
import uuid
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Starting rules, from master context §15; an admin can change or switch off any of them.
DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "name": "Funding, acquisition or expansion",
        "signals": ["acquisition", "expansion", "financing", "funding"],
        "action": "opportunity_detected",
    },
    {
        "name": "New service or product launch",
        "signals": ["new_service", "product_launch"],
        "action": "opportunity_detected",
    },
    {
        "name": "Leadership change",
        "signals": ["cto_hiring", "new_leader"],
        "action": "requires_review",
    },
    {
        "name": "Services or pricing changed on the website",
        "kinds": ["website"],
        "topics": ["pricing", "services"],
        "action": "requires_review",
    },
    {
        "name": "Hiring for product or engineering",
        "signals": ["cto_hiring", "developer_hiring", "product_hiring"],
        "action": "task",
        "task_title": "Follow up on hiring at {account}",
    },
]


def seed_default_rules(conn: sa.Connection) -> None:
    for r in DEFAULT_RULES:
        conn.execute(
            sa.text(
                "INSERT INTO alert_rules (id, name, active, kinds, signals, topics, action,"
                " task_title) VALUES (:id, :name, true, CAST(:kinds AS jsonb),"
                " CAST(:signals AS jsonb), CAST(:topics AS jsonb), :action, :task_title)"
            ),
            {
                "id": uuid.uuid4(),
                "name": r["name"],
                "kinds": json.dumps(r.get("kinds", [])),
                "signals": json.dumps(r.get("signals", [])),
                "topics": json.dumps(r.get("topics", [])),
                "action": r["action"],
                "task_title": r.get("task_title"),
            },
        )


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("kinds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("task_title", sa.String(length=200), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
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
            ["created_by_id"], ["users.id"], name=op.f("fk_alert_rules_created_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_rules")),
    )
    seed_default_rules(op.get_bind())
    op.create_table(
        "notifications",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("link", sa.String(length=300), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_notifications_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id", "created_at"],
        unique=False,
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    op.add_column("monitor_alerts", sa.Column("raised", sa.String(length=30), nullable=True))
    op.add_column(
        "monitor_alerts",
        sa.Column(
            "rules",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column("monitor_alerts", sa.Column("task_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_monitor_alerts_task_id_tasks"), "monitor_alerts", "tasks", ["task_id"], ["id"]
    )
    op.add_column(
        "users",
        sa.Column(
            "notifications_off",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "notifications_off")
    op.drop_constraint(
        op.f("fk_monitor_alerts_task_id_tasks"), "monitor_alerts", type_="foreignkey"
    )
    op.drop_column("monitor_alerts", "task_id")
    op.drop_column("monitor_alerts", "rules")
    op.drop_column("monitor_alerts", "raised")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(
        "ix_notifications_user_unread",
        table_name="notifications",
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.drop_table("notifications")
    op.drop_table("alert_rules")
