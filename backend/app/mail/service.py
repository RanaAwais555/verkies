"""Mailboxes, sending one email, and reading replies back (master context §12B; slice 3.4).

Sending is never automatic. An email goes out only when all of these hold, and the pre-send checks
say which one does not:

- `VROS_EMAIL_SENDING_ENABLED` is on for the whole installation,
- the person has connected their own mailbox, it signs in, and they switched sending on,
- the sending domain passes SPF, DKIM, DMARC and MX,
- the recipient has an email address on a domain that accepts mail, is not suppressed (person,
  domain or account), is not a competitor, and no colleague contacted them in the last 30 days,
- the mailbox is under its daily cap,
- and a person clicks Send.

Every email carries the sender, the company and a one-line opt-out (§12B.7), plus a postal address
for US recipients. Reading replies stores only mail from known contacts or answering an email VROS
sent; nothing else in the inbox enters VROS.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage as MimeMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account, Contact, Suppression
from app.audit import service as audit
from app.auth.models import User
from app.config import Settings
from app.core.enums import (
    AccountType,
    ActivityChannel,
    ActivityDirection,
    ActivityKind,
    AuditSource,
    MailboxStatus,
    MessageDirection,
    MessageStatus,
    SuppressionKind,
    TransportSecurity,
)
from app.core.errors import NotFound, ValidationFailed
from app.crm import timeline
from app.crm.activities import record_activity
from app.crm.models import Activity, Opportunity
from app.deals.models import Deal
from app.mail import crypto
from app.mail.dns_check import DnsChecker, accepts_mail, all_pass, check_sender_domain, domain_of
from app.mail.models import EmailMessage, Mailbox
from app.mail.provider import Inbound, MailboxSettings, MailError, ProviderFactory

COLLEAGUE_WINDOW = timedelta(days=30)
# A reply that says one of these, in its own words rather than in quoted history, is an opt-out.
OPT_OUT = re.compile(
    r"\b(no thanks|no thank you|unsubscribe|remove me|take me off|stop (?:emailing|contacting|"
    r"sending)|do not (?:contact|email)|don't (?:contact|email))\b",
    re.IGNORECASE,
)


def _now() -> datetime:
    return datetime.now(UTC)


# --- mailbox -----------------------------------------------------------------------------------


@dataclass
class MailboxInput:
    address: str
    display_name: str
    smtp_host: str
    smtp_port: int
    smtp_security: TransportSecurity
    imap_host: str
    imap_port: int
    username: str
    password: str | None
    dkim_selector: str | None
    daily_cap: int
    sending_enabled: bool


async def my_mailbox(db: AsyncSession, user: User) -> Mailbox | None:
    return (
        await db.execute(select(Mailbox).where(Mailbox.user_id == user.id))
    ).scalar_one_or_none()


def provider_settings(mailbox: Mailbox, settings: Settings) -> MailboxSettings:
    if not mailbox.secret_encrypted:
        raise ValidationFailed("Connect the mailbox first.", code="mailbox_not_connected")
    return MailboxSettings(
        address=mailbox.address,
        smtp_host=mailbox.smtp_host,
        smtp_port=mailbox.smtp_port,
        smtp_security=mailbox.smtp_security,
        imap_host=mailbox.imap_host,
        imap_port=mailbox.imap_port,
        username=mailbox.username,
        password=crypto.decrypt(settings, mailbox.secret_encrypted),
        timeout=settings.email_timeout_seconds,
    )


async def check(
    mailbox: Mailbox, *, settings: Settings, providers: ProviderFactory, dns: DnsChecker
) -> None:
    """Sign in to SMTP and IMAP, and check the sending domain's DNS. Records the outcome."""
    try:
        await providers(provider_settings(mailbox, settings)).verify()
        mailbox.status = MailboxStatus.CONNECTED
        mailbox.last_error = None
        mailbox.verified_at = _now()
    except MailError as exc:
        mailbox.status = MailboxStatus.FAILING
        mailbox.last_error = str(exc)[:1000]
    mailbox.dns_checks = await check_sender_domain(
        dns, domain_of(mailbox.address), mailbox.dkim_selector
    )
    mailbox.dns_checked_at = _now()


async def save_mailbox(
    db: AsyncSession,
    *,
    user: User,
    data: MailboxInput,
    settings: Settings,
    providers: ProviderFactory,
    dns: DnsChecker,
) -> Mailbox:
    mailbox = await my_mailbox(db, user)
    if mailbox is None and not data.password:
        raise ValidationFailed("Enter the mailbox password to connect it.")
    taken = (
        await db.execute(
            select(Mailbox.id).where(
                func.lower(Mailbox.address) == data.address.lower(), Mailbox.user_id != user.id
            )
        )
    ).first()
    if taken:
        raise ValidationFailed(
            "Someone else has connected that address. VROS never shares a mailbox.",
            code="mailbox_taken",
        )
    fields: dict[str, Any] = {
        "address": data.address.strip().lower(),
        "display_name": data.display_name.strip(),
        "smtp_host": data.smtp_host.strip(),
        "smtp_port": data.smtp_port,
        "smtp_security": data.smtp_security,
        "imap_host": data.imap_host.strip(),
        "imap_port": data.imap_port,
        "username": data.username.strip(),
        "dkim_selector": (data.dkim_selector or "").strip() or None,
        "daily_cap": data.daily_cap,
        "sending_enabled": data.sending_enabled,
    }
    if mailbox is None:
        mailbox = Mailbox(user_id=user.id, **fields)
        db.add(mailbox)
    else:
        for key, value in fields.items():
            setattr(mailbox, key, value)
    if data.password:
        mailbox.secret_encrypted = crypto.encrypt(settings, data.password)
    await check(mailbox, settings=settings, providers=providers, dns=dns)
    await db.flush()
    audit.record(
        db,
        action="mailbox.saved",
        object_table="mailboxes",
        object_id=mailbox.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            **{k: (v.value if hasattr(v, "value") else v) for k, v in fields.items()},
            "password_changed": bool(data.password),
            "status": mailbox.status.value,
        },
    )
    return mailbox


async def disconnect(db: AsyncSession, *, user: User) -> None:
    mailbox = await my_mailbox(db, user)
    if mailbox is None:
        raise NotFound("No mailbox is connected.")
    mailbox.secret_encrypted = None
    mailbox.status = MailboxStatus.DISCONNECTED
    mailbox.sending_enabled = False
    audit.record(
        db,
        action="mailbox.disconnected",
        object_table="mailboxes",
        object_id=mailbox.id,
        user_id=user.id,
        source=AuditSource.API,
    )


# --- pre-send checks ---------------------------------------------------------------------------


@dataclass
class PreflightCheck:
    key: str
    ok: bool
    message: str


@dataclass
class Preflight:
    checks: list[PreflightCheck]
    recipient: str | None
    sender: str | None
    footer: str

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


def footer(sender_name: str, settings: Settings, us_recipient: bool) -> str:
    lines = [
        "--",
        f"{sender_name}, {settings.email_company_name}",
        "If you'd rather not hear from me, reply \"no thanks\" and I won't contact you again.",
    ]
    if us_recipient and settings.email_postal_address:
        lines.append(settings.email_postal_address)
    return "\n".join(lines)


async def _visible_contact(
    db: AsyncSession, user: User, contact_id: uuid.UUID
) -> tuple[Contact, Account]:
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.deleted_at is not None:
        raise NotFound("Contact not found.")
    account = await db.get(Account, contact.account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Contact not found.")
    return contact, account


async def preflight(
    db: AsyncSession, *, user: User, contact_id: uuid.UUID, settings: Settings, dns: DnsChecker
) -> Preflight:
    contact, account = await _visible_contact(db, user, contact_id)
    mailbox = await my_mailbox(db, user)
    checks: list[PreflightCheck] = []

    def add(key: str, ok: bool, good: str, bad: str) -> None:
        checks.append(PreflightCheck(key, ok, good if ok else bad))

    add(
        "sending_enabled",
        settings.email_sending_enabled,
        "Sending is switched on for VROS.",
        "Sending is switched off for VROS. An admin turns it on with VROS_EMAIL_SENDING_ENABLED.",
    )
    connected = mailbox is not None and mailbox.status is MailboxStatus.CONNECTED
    add(
        "mailbox",
        connected,
        f"Your mailbox {mailbox.address if mailbox else ''} is connected.",
        "Connect your mailbox in Settings → Mailbox."
        if mailbox is None or mailbox.status is MailboxStatus.DISCONNECTED
        else "Your mailbox cannot sign in. Check it in Settings → Mailbox.",
    )
    add(
        "mailbox_sending",
        bool(mailbox and mailbox.sending_enabled),
        "You switched sending on for your mailbox.",
        "Switch sending on for your mailbox in Settings → Mailbox.",
    )
    add(
        "sender_dns",
        bool(mailbox and all_pass(mailbox.dns_checks)),
        "Your domain passes SPF, DKIM, DMARC and MX.",
        "Your domain does not yet pass SPF, DKIM, DMARC and MX. See Settings → Mailbox.",
    )
    if mailbox is not None:
        today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = (
            await db.execute(
                select(func.count()).where(
                    EmailMessage.mailbox_id == mailbox.id,
                    EmailMessage.direction == MessageDirection.OUTBOUND,
                    EmailMessage.status.in_((MessageStatus.SENT, MessageStatus.BOUNCED)),
                    EmailMessage.occurred_at >= today,
                )
            )
        ).scalar_one()
        add(
            "daily_cap",
            sent_today < mailbox.daily_cap,
            f"{sent_today} of your {mailbox.daily_cap} emails for today sent.",
            f"You have sent your {mailbox.daily_cap} emails for today.",
        )

    email = (contact.email or "").strip().lower()
    add(
        "recipient",
        bool(email),
        f"{contact.name} has an email address.",
        f"{contact.name} has no email address.",
    )
    if email:
        domain = domain_of(email)
        suppressed = (
            await db.execute(
                select(Suppression.reason).where(
                    or_(
                        (Suppression.kind == SuppressionKind.EMAIL)
                        & (func.lower(Suppression.value) == email),
                        (Suppression.kind == SuppressionKind.DOMAIN)
                        & (func.lower(Suppression.value) == domain),
                        (Suppression.kind == SuppressionKind.ACCOUNT)
                        & (Suppression.value == str(account.id)),
                    )
                )
            )
        ).first()
        add(
            "not_suppressed",
            suppressed is None,
            "Not on the suppression list.",
            f"On the suppression list: {suppressed[0] if suppressed else ''}",
        )
        reachable = await accepts_mail(dns, domain)
        add(
            "recipient_mx",
            reachable == "pass",
            f"{domain} accepts email.",
            f"{domain} has no mail server (MX record)."
            if reachable == "fail"
            else f"Could not check {domain}'s mail server. Try again shortly.",
        )
    add(
        "not_competitor",
        account.account_type is not AccountType.COMPETITOR,
        f"{account.name} is not a competitor.",
        f"{account.name} is marked as a competitor.",
    )
    colleague = (
        await db.execute(
            select(User.name)
            .join(Activity, Activity.actor_id == User.id)
            .where(
                Activity.contact_id == contact.id,
                Activity.actor_id != user.id,
                Activity.direction.in_(
                    (ActivityDirection.OUTBOUND, ActivityDirection.CONVERSATION)
                ),
                Activity.occurred_at >= _now() - COLLEAGUE_WINDOW,
            )
            .limit(1)
        )
    ).first()
    add(
        "no_colleague_contact",
        colleague is None,
        "No colleague has contacted them in the last 30 days.",
        f"{colleague[0] if colleague else 'A colleague'} contacted them in the last 30 days.",
    )
    us = (account.hq_country or "").upper() == "US"
    if us:
        add(
            "postal_address",
            bool(settings.email_postal_address),
            "Your postal address is added for this US company.",
            "This is a US company: set VROS_EMAIL_POSTAL_ADDRESS before emailing it.",
        )
    return Preflight(
        checks=checks,
        recipient=email or None,
        sender=mailbox.address if mailbox else None,
        footer=footer(mailbox.display_name if mailbox else user.name, settings, us),
    )


# --- sending -----------------------------------------------------------------------------------


@dataclass
class Draft:
    contact_id: uuid.UUID
    subject: str
    body: str
    opportunity_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    reply_to_id: uuid.UUID | None = None  # an EmailMessage this answers, to keep the thread


class SendBlocked(ValidationFailed):
    code = "send_blocked"


async def send(
    db: AsyncSession,
    *,
    user: User,
    draft: Draft,
    settings: Settings,
    providers: ProviderFactory,
    dns: DnsChecker,
) -> EmailMessage:
    checks = await preflight(db, user=user, contact_id=draft.contact_id, settings=settings, dns=dns)
    if not checks.ok:
        raise SendBlocked(
            "This email cannot be sent yet.",
            details={"failed": [c.message for c in checks.checks if not c.ok]},
        )
    contact, account = await _visible_contact(db, user, draft.contact_id)
    mailbox = await my_mailbox(db, user)
    assert mailbox is not None  # preflight passed
    deal = await db.get(Deal, draft.deal_id) if draft.deal_id else None
    if deal is not None and deal.account_id != account.id:
        raise ValidationFailed("That deal is not on this contact's account.")
    opportunity_id = draft.opportunity_id or (deal.opportunity_id if deal else None)
    opportunity = await db.get(Opportunity, opportunity_id) if opportunity_id else None
    if opportunity is not None and opportunity.account_id != account.id:
        raise ValidationFailed("That opportunity is not on this contact's account.")
    parent = await db.get(EmailMessage, draft.reply_to_id) if draft.reply_to_id else None
    if parent is not None and parent.account_id != account.id:
        raise ValidationFailed("That email is not on this contact's account.")

    subject = " ".join(draft.subject.split())
    body = f"{draft.body.strip()}\n\n{checks.footer}\n"
    message_id = make_msgid(domain=domain_of(mailbox.address))
    mime = MimeMessage()
    mime["From"] = formataddr((mailbox.display_name, mailbox.address))
    mime["To"] = formataddr((contact.name, checks.recipient or ""))
    mime["Subject"] = subject
    mime["Date"] = format_datetime(_now())
    mime["Message-ID"] = message_id
    if parent is not None:
        mime["In-Reply-To"] = parent.message_id_header
        mime["References"] = f"{parent.thread_key} {parent.message_id_header}".strip()
    mime.set_content(body)

    record = EmailMessage(
        mailbox_id=mailbox.id,
        account_id=account.id,
        contact_id=contact.id,
        opportunity_id=opportunity.id if opportunity else None,
        deal_id=deal.id if deal else None,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.SENT,
        message_id_header=message_id,
        in_reply_to=parent.message_id_header if parent else None,
        thread_key=parent.thread_key if parent else message_id,
        from_address=mailbox.address,
        to_address=checks.recipient or "",
        subject=subject,
        body_text=body,
        occurred_at=_now(),
        sent_by_id=user.id,
    )
    try:
        await providers(provider_settings(mailbox, settings)).send(mime)
    except MailError as exc:
        record.status = MessageStatus.FAILED
        record.error = str(exc)[:1000]
        db.add(record)
        await db.commit()
        raise ValidationFailed(f"The email was not sent. {exc}", code="send_failed") from exc

    db.add(record)
    await db.flush()
    activity = await record_activity(
        db,
        actor_id=user.id,
        account=account,
        contact=contact,
        opportunity=opportunity,
        deal_id=deal.id if deal else None,
        kind=ActivityKind.MESSAGE,
        channel=ActivityChannel.EMAIL,
        direction=ActivityDirection.OUTBOUND,
        occurred_at=record.occurred_at,
        summary=f"{subject}\n\n{draft.body.strip()}",
        headline=f"Email to {contact.name}",
        payload={"email_message_id": str(record.id)},
    )
    record.activity_id = activity.id
    audit.record(
        db,
        action="email.sent",
        object_table="email_messages",
        object_id=record.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"to": record.to_address, "subject": subject, "account_id": str(account.id)},
    )
    return record


# --- reading replies ---------------------------------------------------------------------------


@dataclass
class SyncResult:
    read: int = 0
    stored: int = 0
    opt_outs: int = 0
    bounces: int = 0


def is_opt_out(text: str) -> bool:
    return bool(OPT_OUT.search(text[:600]))


async def _suppress(db: AsyncSession, email: str, reason: str, user_id: uuid.UUID) -> bool:
    exists = (
        await db.execute(
            select(Suppression.id).where(
                Suppression.kind == SuppressionKind.EMAIL, func.lower(Suppression.value) == email
            )
        )
    ).first()
    if exists:
        return False
    db.add(Suppression(kind=SuppressionKind.EMAIL, value=email, reason=reason, added_by_id=user_id))
    return True


async def _bounce(db: AsyncSession, mailbox: Mailbox, item: Inbound) -> bool:
    original = (
        await db.execute(
            select(EmailMessage).where(
                EmailMessage.mailbox_id == mailbox.id,
                EmailMessage.message_id_header == item.bounced_message_id,
                EmailMessage.direction == MessageDirection.OUTBOUND,
            )
        )
    ).scalar_one_or_none()
    if original is None or not (item.bounce_status or "").startswith("5"):
        return False  # not ours, or a temporary failure the server will retry
    original.status = MessageStatus.BOUNCED
    original.error = f"Bounced: delivery status {item.bounce_status}"
    await _suppress(db, original.to_address, f"Hard bounce ({item.bounce_status})", mailbox.user_id)
    timeline.add(
        db,
        account_id=original.account_id,
        event_type="email.bounced",
        summary=f"Email to {original.to_address} bounced ({item.bounce_status}); the address "
        "will not be emailed again.",
        actor_id=None,
        ref_table="email_messages",
        ref_id=original.id,
    )
    return True


async def _match(
    db: AsyncSession, mailbox: Mailbox, item: Inbound
) -> tuple[Account, Contact | None, EmailMessage | None] | None:
    """The account and contact an inbound email belongs to, or None to leave it out of VROS."""
    ids = [i for i in [item.in_reply_to, *item.references] if i]
    parent = None
    if ids:
        parent = (
            await db.execute(
                select(EmailMessage)
                .where(
                    EmailMessage.mailbox_id == mailbox.id, EmailMessage.message_id_header.in_(ids)
                )
                .order_by(EmailMessage.occurred_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if parent is not None:
        account = await db.get(Account, parent.account_id)
        contact = await db.get(Contact, parent.contact_id) if parent.contact_id else None
        return (account, contact, parent) if account else None
    contact = (
        await db.execute(
            select(Contact)
            .join(Account, Account.id == Contact.account_id)
            .where(
                func.lower(Contact.email) == item.from_address,
                Contact.deleted_at.is_(None),
                Account.deleted_at.is_(None),
            )
            .order_by(Contact.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if contact is None:
        return None
    account = await db.get(Account, contact.account_id)
    return (account, contact, None) if account else None


async def sync(
    db: AsyncSession, *, user: User, settings: Settings, providers: ProviderFactory
) -> SyncResult:
    mailbox = await my_mailbox(db, user)
    if mailbox is None or mailbox.status is MailboxStatus.DISCONNECTED:
        raise ValidationFailed("Connect your mailbox first.", code="mailbox_not_connected")
    try:
        fetched = await providers(provider_settings(mailbox, settings)).fetch(
            mailbox.imap_last_uid, mailbox.imap_uidvalidity
        )
    except MailError as exc:
        mailbox.status = MailboxStatus.FAILING
        mailbox.last_error = str(exc)[:1000]
        await db.commit()
        raise ValidationFailed(f"Could not read the mailbox. {exc}", code="sync_failed") from exc

    result = SyncResult(read=len(fetched.messages))
    now = _now()
    for item in fetched.messages:
        if item.from_address == mailbox.address:
            continue  # our own mail, e.g. a copy in the inbox
        if item.is_bounce:
            result.bounces += await _bounce(db, mailbox, item)
            continue
        seen = (
            await db.execute(
                select(EmailMessage.id).where(
                    EmailMessage.mailbox_id == mailbox.id,
                    EmailMessage.message_id_header == item.message_id,
                )
            )
        ).first()
        if seen:
            continue
        matched = await _match(db, mailbox, item)
        if matched is None:
            continue
        account, contact, parent = matched
        occurred = min(item.date or now, now)
        opt_out = not item.auto_reply and is_opt_out(item.text)
        record = EmailMessage(
            mailbox_id=mailbox.id,
            account_id=account.id,
            contact_id=contact.id if contact else None,
            opportunity_id=parent.opportunity_id if parent else None,
            deal_id=parent.deal_id if parent else None,
            direction=MessageDirection.INBOUND,
            status=MessageStatus.RECEIVED,
            message_id_header=item.message_id,
            in_reply_to=item.in_reply_to,
            thread_key=parent.thread_key if parent else item.message_id,
            from_address=item.from_address,
            to_address=mailbox.address,
            subject=item.subject[:2000],
            body_text=item.text[:20000],
            occurred_at=occurred,
            classification="opt_out" if opt_out else "out_of_office" if item.auto_reply else None,
        )
        db.add(record)
        await db.flush()
        name = contact.name if contact else item.from_address
        activity = await record_activity(
            db,
            actor_id=user.id,
            account=account,
            contact=contact,
            opportunity=await db.get(Opportunity, parent.opportunity_id)
            if parent and parent.opportunity_id
            else None,
            deal_id=parent.deal_id if parent else None,
            kind=ActivityKind.MESSAGE,
            channel=ActivityChannel.EMAIL,
            # An automatic reply is recorded, but it is not the person answering.
            direction=ActivityDirection.INTERNAL if item.auto_reply else ActivityDirection.INBOUND,
            occurred_at=occurred,
            summary=f"{item.subject}\n\n{item.text}".strip()[:4000] or "(no text)",
            headline=f"Automatic reply from {name}" if item.auto_reply else f"Email from {name}",
            payload={"email_message_id": str(record.id)},
            source=AuditSource.WORKER,
        )
        record.activity_id = activity.id
        result.stored += 1
        if opt_out and await _suppress(
            db, item.from_address, f"Opted out by reply on {occurred.date().isoformat()}", user.id
        ):
            result.opt_outs += 1
            timeline.add(
                db,
                account_id=account.id,
                event_type="email.opted_out",
                summary=f"{name} asked not to be contacted; {item.from_address} is now suppressed.",
                actor_id=None,
                ref_table="email_messages",
                ref_id=record.id,
            )
    mailbox.imap_uidvalidity = fetched.uidvalidity
    mailbox.imap_last_uid = fetched.last_uid
    mailbox.last_synced_at = now
    if mailbox.status is MailboxStatus.FAILING:
        mailbox.status = MailboxStatus.CONNECTED
        mailbox.last_error = None
    return result


# --- reading -----------------------------------------------------------------------------------


async def list_messages(
    db: AsyncSession,
    *,
    user: User,
    account_id: uuid.UUID | None,
    contact_id: uuid.UUID | None,
    deal_id: uuid.UUID | None,
    limit: int,
) -> list[tuple[EmailMessage, str | None]]:
    if not any((account_id, contact_id, deal_id)):
        raise ValidationFailed("Say whose emails to list.")
    stmt = (
        select(EmailMessage, Contact.name)
        .join(Account, Account.id == EmailMessage.account_id)
        .outerjoin(Contact, Contact.id == EmailMessage.contact_id)
        .where(Account.deleted_at.is_(None))
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    for column, value in (
        (EmailMessage.account_id, account_id),
        (EmailMessage.contact_id, contact_id),
        (EmailMessage.deal_id, deal_id),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    stmt = stmt.order_by(EmailMessage.occurred_at.desc()).limit(limit)
    return [(m, n) for m, n in (await db.execute(stmt)).all()]
