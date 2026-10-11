"""Templates, sequences and enrollments (master context §12A, §12B; slice 3.5).

Nothing here sends anything by itself. A sequence step becomes due on a date; a person then sends
the email, sends the LinkedIn note in their own browser, or makes the call, and records it.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, SmallInteger, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EnrollmentStatus, OutreachChannel, StepOutcome
from app.core.models import Base, CreatedMixin, IdMixin, TimestampMixin, text_enum


class OutreachTemplate(IdMixin, TimestampMixin, Base):
    """Text for an email, a LinkedIn note or a call, with variables such as {first_name}."""

    __tablename__ = "outreach_templates"

    name: Mapped[str] = mapped_column(String(120))
    channel: Mapped[OutreachChannel] = mapped_column(text_enum(OutreachChannel))
    subject: Mapped[str | None] = mapped_column(String(300))  # email only
    body: Mapped[str] = mapped_column(Text)
    # What the template suits, so people can pick the right one; none of these filter anything.
    service_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("services.id"))
    industry: Mapped[str | None] = mapped_column(String(120))
    signal: Mapped[str | None] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Sequence(IdMixin, TimestampMixin, Base):
    __tablename__ = "sequences"

    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class SequenceStep(IdMixin, Base):
    __tablename__ = "sequence_steps"
    __table_args__ = (UniqueConstraint("sequence_id", "position"),)

    sequence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sequences.id"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    channel: Mapped[OutreachChannel] = mapped_column(text_enum(OutreachChannel))
    # Days after the previous step (or after enrolling, for the first step).
    delay_days: Mapped[int] = mapped_column(SmallInteger, default=0)
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outreach_templates.id"))
    instructions: Mapped[str | None] = mapped_column(Text)


class Enrollment(IdMixin, CreatedMixin, Base):
    """A contact going through a sequence. Enrolling is the person's approval of every step;
    each step is still sent or done by a person when it falls due."""

    __tablename__ = "enrollments"
    __table_args__ = (
        # At most one live sequence per contact (§12B.6: not already in an active sequence).
        Index(
            "uq_enrollments_contact_active",
            "contact_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    sequence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sequences.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[EnrollmentStatus] = mapped_column(
        text_enum(EnrollmentStatus), default=EnrollmentStatus.ACTIVE
    )
    stop_reason: Mapped[str | None] = mapped_column(String(200))
    # The position of the step that is due next; past the last step means done.
    next_position: Mapped[int] = mapped_column(SmallInteger, default=0)
    next_due_at: Mapped[datetime | None]
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]


class EnrollmentStep(IdMixin, Base):
    """What a person did at a step: the history of an enrollment."""

    __tablename__ = "enrollment_steps"

    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"), index=True)
    step_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sequence_steps.id"))
    position: Mapped[int] = mapped_column(SmallInteger)
    channel: Mapped[OutreachChannel] = mapped_column(text_enum(OutreachChannel))
    outcome: Mapped[StepOutcome] = mapped_column(text_enum(StepOutcome))
    note: Mapped[str | None] = mapped_column(Text)
    email_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("email_messages.id"))
    activity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("activities.id"))
    done_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    done_at: Mapped[datetime]
