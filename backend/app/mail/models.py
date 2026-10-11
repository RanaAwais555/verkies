"""Mailboxes and the emails sent and received through them (master context §12, §12B; slice 3.4)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    MailboxStatus,
    MailProvider,
    MessageDirection,
    MessageStatus,
    TransportSecurity,
)
from app.core.models import Base, CreatedMixin, IdMixin, TimestampMixin, text_enum


class Mailbox(IdMixin, TimestampMixin, Base):
    """One person's own mailbox. VROS never shares a mailbox between people (§12B).

    The password is stored encrypted (`app/mail/crypto.py`) and never returned by the API.
    """

    __tablename__ = "mailboxes"
    __table_args__ = (UniqueConstraint("user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    address: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[MailProvider] = mapped_column(
        text_enum(MailProvider), default=MailProvider.IMAP_SMTP
    )
    smtp_host: Mapped[str] = mapped_column(String(255))
    smtp_port: Mapped[int]
    smtp_security: Mapped[TransportSecurity] = mapped_column(text_enum(TransportSecurity))
    imap_host: Mapped[str] = mapped_column(String(255))
    imap_port: Mapped[int]
    username: Mapped[str] = mapped_column(String(320))
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    status: Mapped[MailboxStatus] = mapped_column(
        text_enum(MailboxStatus), default=MailboxStatus.UNVERIFIED
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None]
    dkim_selector: Mapped[str | None] = mapped_column(String(63))
    # One entry per check (mx, spf, dkim, dmarc): {"status": "pass", "record": ..., "advice": ...}
    dns_checks: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    dns_checked_at: Mapped[datetime | None]
    # The owner's own switch; sending also needs VROS_EMAIL_SENDING_ENABLED and passing checks.
    sending_enabled: Mapped[bool] = mapped_column(default=False)
    daily_cap: Mapped[int] = mapped_column(SmallInteger, default=20)
    imap_uidvalidity: Mapped[int | None] = mapped_column(BigInteger)
    imap_last_uid: Mapped[int | None] = mapped_column(BigInteger)
    last_synced_at: Mapped[datetime | None]


class EmailMessage(IdMixin, CreatedMixin, Base):
    """An email VROS sent, or a reply it matched to a contact or a thread it started.

    Nothing else in the inbox is read into VROS: an inbound message is stored only when it comes
    from a known contact's address or answers an email VROS sent.
    """

    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("mailbox_id", "message_id_header"),
        Index("ix_email_messages_account_time", "account_id", "occurred_at"),
    )

    mailbox_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mailboxes.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id"), index=True)
    direction: Mapped[MessageDirection] = mapped_column(text_enum(MessageDirection))
    status: Mapped[MessageStatus] = mapped_column(text_enum(MessageStatus))
    message_id_header: Mapped[str] = mapped_column(String(998))
    in_reply_to: Mapped[str | None] = mapped_column(String(998))
    # The Message-ID of the first email in the thread, so replies group with what they answer.
    thread_key: Mapped[str] = mapped_column(String(998), index=True)
    from_address: Mapped[str] = mapped_column(String(320))
    to_address: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime]
    sent_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    activity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("activities.id"))
    error: Mapped[str | None] = mapped_column(Text)
    # Set on inbound mail VROS acted on: "opt_out" (the address was suppressed) or "bounce".
    classification: Mapped[str | None] = mapped_column(String(40))
