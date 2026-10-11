"""/mailbox and /email: connect your own mailbox, check before sending, send one email, read
replies (slice 3.4)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from app.accounts.models import Contact
from app.auth.deps import AppSettings, DbSession, require_permission
from app.auth.models import User
from app.core.enums import TransportSecurity
from app.core.errors import NotFound
from app.mail import service
from app.mail.dns_check import DnsChecker, DnsPythonChecker, all_pass
from app.mail.models import EmailMessage, Mailbox
from app.mail.provider import ProviderFactory, imap_smtp

router = APIRouter(tags=["email"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]


def get_mail_providers() -> ProviderFactory:
    """How mailboxes are reached. Tests override this with a fake."""
    return imap_smtp


def get_dns_checker() -> DnsChecker:
    return DnsPythonChecker()


Providers = Annotated[ProviderFactory, Depends(get_mail_providers)]
Dns = Annotated[DnsChecker, Depends(get_dns_checker)]
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
HOST = r"^[A-Za-z0-9.-]+$"


class MailboxOut(BaseModel):
    address: str
    display_name: str
    provider: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    imap_host: str
    imap_port: int
    username: str
    has_password: bool
    status: str
    last_error: str | None
    verified_at: datetime | None
    dkim_selector: str | None
    dns_checks: dict[str, Any]
    dns_checked_at: datetime | None
    dns_ok: bool
    sending_enabled: bool
    daily_cap: int
    last_synced_at: datetime | None
    sending_allowed_by_admin: bool

    @classmethod
    def of(cls, m: Mailbox, enabled: bool) -> "MailboxOut":
        return cls(
            address=m.address,
            display_name=m.display_name,
            provider=m.provider.value,
            smtp_host=m.smtp_host,
            smtp_port=m.smtp_port,
            smtp_security=m.smtp_security.value,
            imap_host=m.imap_host,
            imap_port=m.imap_port,
            username=m.username,
            has_password=bool(m.secret_encrypted),
            status=m.status.value,
            last_error=m.last_error,
            verified_at=m.verified_at,
            dkim_selector=m.dkim_selector,
            dns_checks=m.dns_checks or {},
            dns_checked_at=m.dns_checked_at,
            dns_ok=all_pass(m.dns_checks or {}),
            sending_enabled=m.sending_enabled,
            daily_cap=m.daily_cap,
            last_synced_at=m.last_synced_at,
            sending_allowed_by_admin=enabled,
        )


class MailboxIn(BaseModel):
    address: str = Field(max_length=320, pattern=EMAIL)
    display_name: str = Field(min_length=1, max_length=200)
    smtp_host: str = Field(min_length=1, max_length=255, pattern=HOST)
    smtp_port: int = Field(ge=1, le=65535)
    smtp_security: TransportSecurity
    imap_host: str = Field(min_length=1, max_length=255, pattern=HOST)
    imap_port: int = Field(ge=1, le=65535)
    username: str = Field(min_length=1, max_length=320)
    # Omit to keep the stored password. Never returned.
    password: str | None = Field(default=None, max_length=1000)
    dkim_selector: str | None = Field(default=None, max_length=63, pattern=r"^[A-Za-z0-9._-]*$")
    daily_cap: int = Field(default=20, ge=1, le=500)
    sending_enabled: bool = False


class MailboxState(BaseModel):
    mailbox: MailboxOut | None
    sending_allowed_by_admin: bool


@router.get("/mailbox")
async def get_mailbox(user: Member, db: DbSession, settings: AppSettings) -> MailboxState:
    mailbox = await service.my_mailbox(db, user)
    enabled = settings.email_sending_enabled
    return MailboxState(
        mailbox=MailboxOut.of(mailbox, enabled) if mailbox else None,
        sending_allowed_by_admin=enabled,
    )


@router.put("/mailbox")
async def save_mailbox(
    body: MailboxIn,
    user: Member,
    db: DbSession,
    settings: AppSettings,
    providers: Providers,
    dns: Dns,
) -> MailboxOut:
    mailbox = await service.save_mailbox(
        db,
        user=user,
        data=service.MailboxInput(**body.model_dump()),
        settings=settings,
        providers=providers,
        dns=dns,
    )
    await db.commit()
    return MailboxOut.of(mailbox, settings.email_sending_enabled)


@router.post("/mailbox/check")
async def check_mailbox(
    user: Member, db: DbSession, settings: AppSettings, providers: Providers, dns: Dns
) -> MailboxOut:
    mailbox = await service.my_mailbox(db, user)
    if mailbox is None:
        raise NotFound("No mailbox is connected.")
    await service.check(mailbox, settings=settings, providers=providers, dns=dns)
    await db.commit()
    return MailboxOut.of(mailbox, settings.email_sending_enabled)


@router.delete("/mailbox", status_code=204)
async def disconnect_mailbox(user: Member, db: DbSession) -> Response:
    await service.disconnect(db, user=user)
    await db.commit()
    return Response(status_code=204)


class SyncOut(BaseModel):
    read: int
    stored: int
    opt_outs: int
    bounces: int


@router.post("/mailbox/sync")
async def sync_mailbox(
    user: Member, db: DbSession, settings: AppSettings, providers: Providers
) -> SyncOut:
    result = await service.sync(db, user=user, settings=settings, providers=providers)
    await db.commit()
    return SyncOut(**result.__dict__)


class CheckOut(BaseModel):
    key: str
    ok: bool
    message: str


class PreflightOut(BaseModel):
    ok: bool
    checks: list[CheckOut]
    recipient: str | None
    sender: str | None
    footer: str


@router.get("/email/preflight")
async def email_preflight(
    contact_id: uuid.UUID, user: Member, db: DbSession, settings: AppSettings, dns: Dns
) -> PreflightOut:
    found = await service.preflight(
        db, user=user, contact_id=contact_id, settings=settings, dns=dns
    )
    return PreflightOut(
        ok=found.ok,
        checks=[CheckOut(**c.__dict__) for c in found.checks],
        recipient=found.recipient,
        sender=found.sender,
        footer=found.footer,
    )


class EmailOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    contact_id: uuid.UUID | None
    contact_name: str | None
    opportunity_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    direction: str
    status: str
    from_address: str
    to_address: str
    subject: str
    body_text: str
    occurred_at: datetime
    thread_key: str
    classification: str | None
    error: str | None

    @classmethod
    def of(cls, m: EmailMessage, contact_name: str | None) -> "EmailOut":
        return cls(
            id=m.id,
            account_id=m.account_id,
            contact_id=m.contact_id,
            contact_name=contact_name,
            opportunity_id=m.opportunity_id,
            deal_id=m.deal_id,
            direction=m.direction.value,
            status=m.status.value,
            from_address=m.from_address,
            to_address=m.to_address,
            subject=m.subject,
            body_text=m.body_text,
            occurred_at=m.occurred_at,
            thread_key=m.thread_key,
            classification=m.classification,
            error=m.error,
        )


class SendIn(BaseModel):
    contact_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    opportunity_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    reply_to_id: uuid.UUID | None = None


@router.post("/email/send", status_code=201)
async def send_email(
    body: SendIn, user: Member, db: DbSession, settings: AppSettings, providers: Providers, dns: Dns
) -> EmailOut:
    message = await service.send(
        db,
        user=user,
        draft=service.Draft(**body.model_dump()),
        settings=settings,
        providers=providers,
        dns=dns,
    )
    await db.commit()
    contact = await db.get(Contact, message.contact_id) if message.contact_id else None
    contact_name = contact.name if contact else None
    return EmailOut.of(message, contact_name)


@router.get("/email/messages")
async def list_emails(
    user: Member,
    db: DbSession,
    account_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[EmailOut]:
    rows = await service.list_messages(
        db, user=user, account_id=account_id, contact_id=contact_id, deal_id=deal_id, limit=limit
    )
    return [EmailOut.of(m, name) for m, name in rows]
