"""clients and projects: projects, milestones and project risks, tasks.project_id, and the
account manager and client-since date on accounts (slice 4.1)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-12

Converting a won deal keeps the same account; nothing here copies or moves history.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("deal_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=True),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "not_started",
                "planning",
                "active",
                "at_risk",
                "on_hold",
                "completed",
                "cancelled",
                name="projectstatus",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "target_date IS NULL OR start_date IS NULL OR target_date >= start_date",
            name=op.f("ck_projects_target_after_start"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_projects_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], name=op.f("fk_projects_deal_id_deals")),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_projects_owner_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["services.id"], name=op.f("fk_projects_service_id_services")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_account_id"), "projects", ["account_id"], unique=False)
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"], unique=False)
    op.create_index(op.f("ix_projects_status"), "projects", ["status"], unique=False)
    op.create_index(
        "uq_projects_deal_live",
        "projects",
        ["deal_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND deal_id IS NOT NULL"),
    )
    op.create_table(
        "milestones",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_id", sa.UUID(), nullable=True),
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
            ["completed_by_id"], ["users.id"], name=op.f("fk_milestones_completed_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_milestones_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestones")),
    )
    op.create_index(op.f("ix_milestones_project_id"), "milestones", ["project_id"], unique=False)
    op.create_table(
        "project_risks",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "low",
                "medium",
                "high",
                name="riskseverity",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("raised_by_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_id", sa.UUID(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
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
            ["project_id"], ["projects.id"], name=op.f("fk_project_risks_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["raised_by_id"], ["users.id"], name=op.f("fk_project_risks_raised_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_id"], ["users.id"], name=op.f("fk_project_risks_resolved_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_risks")),
    )
    op.create_index(
        op.f("ix_project_risks_project_id"), "project_risks", ["project_id"], unique=False
    )
    op.add_column("accounts", sa.Column("account_manager_id", sa.UUID(), nullable=True))
    op.add_column("accounts", sa.Column("client_since", sa.Date(), nullable=True))
    op.create_foreign_key(
        op.f("fk_accounts_account_manager_id_users"),
        "accounts",
        "users",
        ["account_manager_id"],
        ["id"],
    )
    op.add_column("tasks", sa.Column("project_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_tasks_project_id"), "tasks", ["project_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_tasks_project_id_projects"), "tasks", "projects", ["project_id"], ["id"]
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_constraint(op.f("fk_tasks_project_id_projects"), "tasks", type_="foreignkey")
    op.drop_index(op.f("ix_tasks_project_id"), table_name="tasks")
    op.drop_column("tasks", "project_id")
    op.drop_constraint(op.f("fk_accounts_account_manager_id_users"), "accounts", type_="foreignkey")
    op.drop_column("accounts", "client_since")
    op.drop_column("accounts", "account_manager_id")
    op.drop_index(op.f("ix_project_risks_project_id"), table_name="project_risks")
    op.drop_table("project_risks")
    op.drop_index(op.f("ix_milestones_project_id"), table_name="milestones")
    op.drop_table("milestones")
    op.drop_index(
        "uq_projects_deal_live",
        table_name="projects",
        postgresql_where=sa.text("deleted_at IS NULL AND deal_id IS NOT NULL"),
    )
    op.drop_index(op.f("ix_projects_status"), table_name="projects")
    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_account_id"), table_name="projects")
    op.drop_table("projects")
    # ### end Alembic commands ###
