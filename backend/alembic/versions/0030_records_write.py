"""records.write: changing records needs its own permission, so Viewer is read-only (slice 7.4)

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-13

Until now every role that could see accounts could also change them: the routes that create or
edit people, activities, tasks, deals, projects and the rest asked only for accounts.read or
accounts.read_own. Viewer is meant to be read-only, so changing a record now also needs
records.write (app/auth/deps.require_permission), granted to every role except Viewer.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = (
    "records.write",
    "Create and change accounts, people, activities, tasks, deals, projects and other records",
)
GRANTED_TO = (
    "admin",
    "founder",
    "sales_manager",
    "salesperson",
    "researcher",
    "project_manager",
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO permissions (id, key, description) VALUES (gen_random_uuid(), :k, :d)"
        ),
        {"k": PERMISSION[0], "d": PERMISSION[1]},
    )
    conn.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, p.id FROM roles r,"
            " permissions p WHERE r.key = ANY(:roles) AND p.key = :k"
        ),
        {"roles": list(GRANTED_TO), "k": PERMISSION[0]},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN"
            " (SELECT id FROM permissions WHERE key = :k)"
        ),
        {"k": PERMISSION[0]},
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE key = :k"), {"k": PERMISSION[0]})
