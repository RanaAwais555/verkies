"""outreach: templates, sequences, enrollments and their history, the 'outreach.manage' permission,
and the default sequence of master context §12B.4 (slice 3.5)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-12

The default templates use variables only, filled from the contact, the account and its lead brief;
a variable VROS does not know is left for the person to write. Every step is done by a person.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = ("outreach.manage", "Create and change outreach templates and sequences")
GRANTED_TO = ("admin", "founder", "sales_manager")

# (key, name, channel, subject, body). A follow-up email with no subject replies in the thread.
TEMPLATES = [
    (
        "first_email",
        "First email",
        "email",
        "{company} and {service}",
        "Hi {first_name},\n\n{why_now}\n\n{problem}\n\nWe did similar work for {similar_project}. "
        "Would a short call next week be useful?\n\n{sender_name}",
    ),
    (
        "linkedin_note",
        "LinkedIn connection note",
        "linkedin",
        None,
        "Hi {first_name}, I came across {company} and would like to connect. {sender_name}",
    ),
    (
        "follow_up",
        "Follow-up email",
        "email",
        None,
        "Hi {first_name},\n\nFollowing up on my email last week. Would a 20-minute call be "
        "useful?\n\n{sender_name}",
    ),
    (
        "final_note",
        "Final note",
        "email",
        None,
        "Hi {first_name},\n\nI won't keep writing. If {service} becomes a priority for {company}, "
        "I'm happy to help.\n\n{sender_name}",
    ),
]

# (channel, days after the previous step, template key or None, instructions for a call)
DEFAULT_STEPS = [
    ("email", 0, "first_email", None),
    ("linkedin", 2, "linkedin_note", None),
    ("email", 2, "follow_up", None),
    (
        "call",
        3,
        None,
        "Call {first_name}, or send a LinkedIn message: ask whether the emails arrived.",
    ),
    ("email", 4, "final_note", None),
]


def seed_default_sequence(conn: sa.Connection) -> None:
    """The default templates and sequence. Also used by the tests to restore them."""
    ids = {}
    for key, name, channel, subject, body in TEMPLATES:
        ids[key] = conn.execute(
            sa.text(
                "INSERT INTO outreach_templates (id, name, channel, subject, body, is_active,"
                " created_at, updated_at) VALUES (gen_random_uuid(), :n, :c, :s, :b, true, now(),"
                " now()) RETURNING id"
            ),
            {"n": name, "c": channel, "s": subject, "b": body},
        ).scalar_one()
    sequence = conn.execute(
        sa.text(
            "INSERT INTO sequences (id, name, description, is_active, created_at, updated_at)"
            " VALUES (gen_random_uuid(), :n, :d, true, now(), now()) RETURNING id"
        ),
        {
            "n": "Default outreach",
            "d": "Master context §12B.4: email, LinkedIn note, follow-up, a call, a final note.",
        },
    ).scalar_one()
    for position, (channel, delay, template, instructions) in enumerate(DEFAULT_STEPS):
        conn.execute(
            sa.text(
                "INSERT INTO sequence_steps (id, sequence_id, position, channel, delay_days,"
                " template_id, instructions) VALUES (gen_random_uuid(), :s, :p, :c, :d, :t, :i)"
            ),
            {
                "s": sequence,
                "p": position,
                "c": channel,
                "d": delay,
                "t": ids[template] if template else None,
                "i": instructions,
            },
        )


def upgrade() -> None:
    op.create_table(
        "outreach_templates",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "channel",
            sa.Enum(
                "email",
                "linkedin",
                "call",
                name="outreachchannel",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=300), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("signal", sa.String(length=60), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
            ["created_by_id"], ["users.id"], name=op.f("fk_outreach_templates_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["services.id"], name=op.f("fk_outreach_templates_service_id_services")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outreach_templates")),
    )
    op.create_table(
        "sequences",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
            ["created_by_id"], ["users.id"], name=op.f("fk_sequences_created_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sequences")),
    )
    op.create_table(
        "sequence_steps",
        sa.Column("sequence_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum(
                "email",
                "linkedin",
                "call",
                name="outreachchannel",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("delay_days", sa.SmallInteger(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sequence_id"], ["sequences.id"], name=op.f("fk_sequence_steps_sequence_id_sequences")
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["outreach_templates.id"],
            name=op.f("fk_sequence_steps_template_id_outreach_templates"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sequence_steps")),
        sa.UniqueConstraint(
            "sequence_id", "position", name=op.f("uq_sequence_steps_sequence_id_position")
        ),
    )
    op.create_index(
        op.f("ix_sequence_steps_sequence_id"), "sequence_steps", ["sequence_id"], unique=False
    )
    op.create_table(
        "enrollments",
        sa.Column("sequence_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "completed",
                "stopped",
                name="enrollmentstatus",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("stop_reason", sa.String(length=200), nullable=True),
        sa.Column("next_position", sa.SmallInteger(), nullable=False),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_enrollments_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_id"], ["users.id"], name=op.f("fk_enrollments_approved_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["contacts.id"], name=op.f("fk_enrollments_contact_id_contacts")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_enrollments_owner_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["sequence_id"], ["sequences.id"], name=op.f("fk_enrollments_sequence_id_sequences")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollments")),
    )
    op.create_index(op.f("ix_enrollments_account_id"), "enrollments", ["account_id"], unique=False)
    op.create_index(op.f("ix_enrollments_contact_id"), "enrollments", ["contact_id"], unique=False)
    op.create_index(op.f("ix_enrollments_owner_id"), "enrollments", ["owner_id"], unique=False)
    op.create_index(
        op.f("ix_enrollments_sequence_id"), "enrollments", ["sequence_id"], unique=False
    )
    op.create_index(
        "uq_enrollments_contact_active",
        "enrollments",
        ["contact_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "enrollment_steps",
        sa.Column("enrollment_id", sa.UUID(), nullable=False),
        sa.Column("step_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum(
                "email",
                "linkedin",
                "call",
                name="outreachchannel",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                "sent",
                "called",
                "skipped",
                "wrong_person",
                "already_connected",
                name="stepoutcome",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("email_message_id", sa.UUID(), nullable=True),
        sa.Column("activity_id", sa.UUID(), nullable=True),
        sa.Column("done_by_id", sa.UUID(), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.id"],
            name=op.f("fk_enrollment_steps_activity_id_activities"),
        ),
        sa.ForeignKeyConstraint(
            ["done_by_id"], ["users.id"], name=op.f("fk_enrollment_steps_done_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["email_message_id"],
            ["email_messages.id"],
            name=op.f("fk_enrollment_steps_email_message_id_email_messages"),
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id"],
            ["enrollments.id"],
            name=op.f("fk_enrollment_steps_enrollment_id_enrollments"),
        ),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["sequence_steps.id"],
            name=op.f("fk_enrollment_steps_step_id_sequence_steps"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollment_steps")),
    )
    op.create_index(
        op.f("ix_enrollment_steps_enrollment_id"),
        "enrollment_steps",
        ["enrollment_id"],
        unique=False,
    )
    conn = op.get_bind()
    seed_default_sequence(conn)
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

    op.drop_index(op.f("ix_enrollment_steps_enrollment_id"), table_name="enrollment_steps")
    op.drop_table("enrollment_steps")
    op.drop_index(
        "uq_enrollments_contact_active",
        table_name="enrollments",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_index(op.f("ix_enrollments_sequence_id"), table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_owner_id"), table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_contact_id"), table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_account_id"), table_name="enrollments")
    op.drop_table("enrollments")
    op.drop_index(op.f("ix_sequence_steps_sequence_id"), table_name="sequence_steps")
    op.drop_table("sequence_steps")
    op.drop_table("sequences")
    op.drop_table("outreach_templates")
