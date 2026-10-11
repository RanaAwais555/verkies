"""The EmailProvider interface (PROVIDER_SPEC.md) and its first implementation, IMAP + SMTP.

Gmail and Microsoft Graph (OAuth) implement the same interface later. The standard library's
`smtplib` and `imaplib` are blocking, so each call runs in a worker thread with a timeout. Tests
replace the provider with a fake through the router's dependency.
"""

import asyncio
import email
import imaplib
import re
import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage as MimeMessage
from email.message import Message
from email.policy import default as default_policy
from email.utils import getaddresses, parsedate_to_datetime
from typing import Protocol

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.core.enums import TransportSecurity

FIRST_SYNC_DAYS = 14  # a newly connected mailbox is read back this far, no further
MAX_PER_SYNC = 200


class MailError(Exception):
    """The mail server refused or could not be reached. The message is safe to show the user."""


@dataclass
class MailboxSettings:
    address: str
    smtp_host: str
    smtp_port: int
    smtp_security: TransportSecurity
    imap_host: str
    imap_port: int
    username: str
    password: str
    timeout: float = 20.0


@dataclass
class Inbound:
    uid: int
    message_id: str
    in_reply_to: str | None
    references: list[str]
    from_address: str
    to_addresses: list[str]
    subject: str
    text: str  # the new part of the message, with quoted history cut off
    date: datetime | None
    # A delivery status notification about an email VROS sent.
    is_bounce: bool = False
    bounce_status: str | None = None  # e.g. "5.1.1"; a 5.x.x status is a hard bounce
    bounced_message_id: str | None = None
    # An automatic reply (out of office, holiday): not the person answering.
    auto_reply: bool = False


@dataclass
class FetchResult:
    uidvalidity: int
    last_uid: int | None
    messages: list[Inbound] = field(default_factory=list)


class EmailProvider(Protocol):
    async def verify(self) -> None: ...
    async def send(self, message: MimeMessage) -> None: ...
    async def fetch(self, since_uid: int | None, uidvalidity: int | None) -> FetchResult: ...


ProviderFactory = Callable[[MailboxSettings], EmailProvider]


# --- parsing -----------------------------------------------------------------------------------

_QUOTE_START = re.compile(
    r"^(>|On .{4,200}wrote:\s*$|-{2,}\s*Original Message|From: .+|Sent from my )", re.IGNORECASE
)


def _ids(value: str | None) -> list[str]:
    return re.findall(r"<[^<>\s]+>", value or "")


def new_text(text: str) -> str:
    """The reply itself: everything before the quoted earlier message."""
    kept = []
    for line in text.splitlines():
        if _QUOTE_START.match(line.strip()):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def _text_of(message: Message) -> str:
    part = (
        message.get_body(preferencelist=("plain", "html")) if hasattr(message, "get_body") else None
    )
    if part is None:
        return ""
    content = part.get_content()
    if part.get_content_type() == "text/html":
        content = HTMLParser(content).text(separator="\n")
    return str(content)


def _bounce(message: Message) -> tuple[str | None, str | None]:
    """Status and original Message-ID from a delivery status notification (RFC 3464)."""
    status = original = None
    for part in message.walk():
        kind = part.get_content_type()
        if kind == "message/delivery-status":
            payload = part.get_payload()
            blocks = payload if isinstance(payload, list) else [part]
            for block in blocks:
                found = re.search(r"^Status:\s*([245]\.\d+\.\d+)", str(block), re.MULTILINE)
                if found:
                    status = found.group(1)
        elif kind in ("message/rfc822", "text/rfc822-headers"):
            found = re.search(r"^Message-ID:\s*(<[^>]+>)", str(part), re.MULTILINE | re.IGNORECASE)
            if found:
                original = found.group(1)
    return status, original


_AUTO_SUBJECT = re.compile(
    r"^(automatic reply|auto(?:matic)?[- ]?reply|out of (?:the )?office|auto:)", re.IGNORECASE
)


def is_auto_reply(message: Message) -> bool:
    """RFC 3834's Auto-Submitted header, the common vendor headers, or a tell-tale subject."""
    submitted = str(message.get("Auto-Submitted", "no")).strip().lower()
    if submitted and submitted != "no":
        return True
    if any(message.get(h) for h in ("X-Autoreply", "X-Autorespond", "X-Auto-Response-Suppress")):
        return True
    return bool(_AUTO_SUBJECT.match(str(message.get("Subject", "")).strip()))


def parse_inbound(uid: int, raw: bytes) -> Inbound:
    message = email.message_from_bytes(raw, policy=default_policy)
    sender = getaddresses([str(message.get("From", ""))])
    recipients = getaddresses([str(message.get("To", "")), str(message.get("Cc", ""))])
    try:
        date = parsedate_to_datetime(str(message["Date"])) if message["Date"] else None
    except (TypeError, ValueError):
        date = None
    if date is not None and date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    is_report = message.get_content_type() == "multipart/report"
    status, original = _bounce(message) if is_report else (None, None)
    message_id = (_ids(str(message.get("Message-ID", ""))) or [f"<vros-uid-{uid}@unknown>"])[0]
    return Inbound(
        uid=uid,
        message_id=message_id,
        in_reply_to=next(iter(_ids(str(message.get("In-Reply-To", "")))), None),
        references=_ids(str(message.get("References", ""))),
        from_address=(sender[0][1] if sender else "").lower(),
        to_addresses=[a.lower() for _, a in recipients if a],
        subject=str(message.get("Subject", "")),
        text=new_text(_text_of(message)) if not is_report else "",
        date=date,
        is_bounce=is_report and status is not None,
        bounce_status=status,
        bounced_message_id=original,
        auto_reply=not is_report and is_auto_reply(message),
    )


# --- IMAP + SMTP -------------------------------------------------------------------------------


class ImapSmtpProvider:
    def __init__(self, settings: MailboxSettings) -> None:
        self.s = settings

    def _smtp(self) -> smtplib.SMTP:
        context = ssl.create_default_context()
        if self.s.smtp_security is TransportSecurity.SSL:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                self.s.smtp_host, self.s.smtp_port, timeout=self.s.timeout, context=context
            )
        else:
            smtp = smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=self.s.timeout)
            smtp.starttls(context=context)
        smtp.login(self.s.username, self.s.password)
        return smtp

    def _imap(self) -> imaplib.IMAP4_SSL:
        imap = imaplib.IMAP4_SSL(
            self.s.imap_host,
            self.s.imap_port,
            ssl_context=ssl.create_default_context(),
            timeout=self.s.timeout,
        )
        imap.login(self.s.username, self.s.password)
        return imap

    async def _run[T](self, fn: Callable[[], T]) -> T:
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn), self.s.timeout + 5)
        except (smtplib.SMTPAuthenticationError, imaplib.IMAP4.error) as exc:
            raise MailError(f"The server refused the sign-in: {exc}") from exc
        except (TimeoutError, OSError, smtplib.SMTPException, ssl.SSLError) as exc:
            raise MailError(f"Could not reach the mail server: {exc}") from exc

    async def verify(self) -> None:
        def check() -> None:
            with self._smtp():
                pass
            imap = self._imap()
            try:
                imap.select("INBOX", readonly=True)
            finally:
                imap.logout()

        await self._run(check)

    async def send(self, message: MimeMessage) -> None:
        def deliver() -> None:
            with self._smtp() as smtp:
                smtp.send_message(message)

        await self._run(deliver)

    async def fetch(self, since_uid: int | None, uidvalidity: int | None) -> FetchResult:
        def read() -> FetchResult:
            imap = self._imap()
            try:
                imap.select("INBOX", readonly=True)
                _, data = imap.response("UIDVALIDITY")
                validity = int(data[0]) if data and data[0] else 0
                if since_uid is not None and uidvalidity == validity:
                    _, found = imap.uid("SEARCH", f"UID {since_uid + 1}:*")
                else:
                    since = (datetime.now(UTC) - timedelta(days=FIRST_SYNC_DAYS)).strftime(
                        "%d-%b-%Y"
                    )
                    _, found = imap.uid("SEARCH", f"SINCE {since}")
                uids = sorted(int(u) for u in (found[0] or b"").split())
                if since_uid is not None and uidvalidity == validity:
                    uids = [u for u in uids if u > since_uid]  # "n:*" always returns the last one
                uids = uids[:MAX_PER_SYNC]
                messages = []
                for uid in uids:
                    _, parts = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
                    raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
                    if raw:
                        messages.append(parse_inbound(uid, raw))
                last = uids[-1] if uids else since_uid if uidvalidity == validity else None
                return FetchResult(validity, last, messages)
            finally:
                imap.logout()

        return await self._run(read)


def imap_smtp(settings: MailboxSettings) -> EmailProvider:
    return ImapSmtpProvider(settings)
