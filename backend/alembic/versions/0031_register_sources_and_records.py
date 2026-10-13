"""register sources and records: regulators' registers kept in VROS and refreshed by the
worker, and discovery jobs searched from them (slice 8.1)

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_OLD = ("csv_import", "search", "registry")
KINDS_NEW = (*KINDS_OLD, "register")


def _kinds(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_discovery_jobs_discoverykind"), "discovery_jobs", type_="check")
    listed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint("discoverykind", "discovery_jobs", f"kind IN ({listed})")


def upgrade() -> None:
    op.create_table(
        "register_sources",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_status",
            sa.Enum(
                "ok",
                "unchanged",
                "failed",
                "unconfigured",
                name="registerrefreshstatus",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=True,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("active_count", sa.Integer(), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.PrimaryKeyConstraint("key", name=op.f("pk_register_sources")),
    )
    op.create_table(
        "register_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=True),
        sa.Column("legal_form", sa.String(length=80), nullable=True),
        sa.Column("company_number", sa.String(length=8), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("postcode", sa.String(length=12), nullable=True),
        sa.Column("town", sa.String(length=120), nullable=True),
        sa.Column("postcode_areas", postgresql.ARRAY(sa.String(length=2)), nullable=False),
        sa.Column("areas", postgresql.ARRAY(sa.String(length=120)), nullable=False),
        sa.Column("office_count", sa.Integer(), nullable=True),
        sa.Column("authorised_on", sa.Date(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_register_records")),
        sa.UniqueConstraint(
            "source", "source_id", name=op.f("uq_register_records_source_source_id")
        ),
    )
    op.create_index(
        op.f("ix_register_records_company_number"),
        "register_records",
        ["company_number"],
        unique=False,
    )
    op.create_index(
        "ix_register_records_source_active", "register_records", ["source", "active"], unique=False
    )
    _kinds(KINDS_NEW)


def downgrade() -> None:
    op.execute("DELETE FROM discovery_jobs WHERE kind = 'register'")
    _kinds(KINDS_OLD)
    op.drop_index("ix_register_records_source_active", table_name="register_records")
    op.drop_index(op.f("ix_register_records_company_number"), table_name="register_records")
    op.drop_table("register_records")
    op.drop_table("register_sources")
