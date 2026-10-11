"""Slice 3.4: mailbox connection, the checks before sending, sending one email, reading replies.

The mail server and DNS are fakes, swapped in through the router's dependencies.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from email.message import EmailMessage as MimeMessage

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.config import Settings, get_settings
from app.mail.dns_check import DnsUnavailable
from app.mail.provider import FetchResult, Inbound, MailboxSettings, MailError
from app.mail.router import get_dns_checker, get_mail_providers
from app.main import create_app
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_activities import contact, log
from tests.integration.test_leads import account, opportunity

pytestmark = pytest.mark.integration

PASSWORD = "app-password-for-tests"  # noqa: S105 - a fake server's password
NOW = datetime.now(UTC)


class FakeServer:
    """Records what VROS sends and serves the inbox a test puts in it."""

    def __init__(self) -> None:
        self.sent: list[MimeMessage] = []
        self.inbox: list[Inbound] = []
        self.refuse_login = False
        self.refuse_send = False
        self.logins: list[MailboxSettings] = []

    def factory(self, settings: MailboxSettings) -> "FakeProvider":
        self.logins.append(settings)
        return FakeProvider(self)


class FakeProvider:
    def __init__(self, server: FakeServer) -> None:
        self.server = server

    async def verify(self) -> None:
        if self.server.refuse_login:
            raise MailError("The server refused the sign-in: bad password")

    async def send(self, message: MimeMessage) -> None:
        if self.server.refuse_send:
            raise MailError("Could not reach the mail server: timed out")
        self.server.sent.append(message)

    async def fetch(self, since_uid: int | None, uidvalidity: int | None) -> FetchResult:
        new = [m for m in self.server.inbox if since_uid is None or m.uid > since_uid]
        return FetchResult(1, max((m.uid for m in self.server.inbox), default=since_uid), new)


GOOD_DNS = {
    "verkies.test": ["v=spf1 include:_spf.google.com ~all"],
    "_dmarc.verkies.test": ["v=DMARC1; p=quarantine"],
    "google._domainkey.verkies.test": ["v=DKIM1; k=rsa; p=MIIBIjANBg"],
}


class FakeDns:
    def __init__(self) -> None:
        self.records = dict(GOOD_DNS)
        self.no_mx: set[str] = set()

    async def txt(self, name: str) -> list[str]:
        return self.records.get(name, [])

    async def mx(self, domain: str) -> list[str]:
        if domain == "down.test":
            raise DnsUnavailable("timeout")
        return [] if domain in self.no_mx else [f"mx.{domain}"]


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def dns() -> FakeDns:
    return FakeDns()


@pytest.fixture
def enabled() -> Settings:
    return get_settings().model_copy(update={"email_sending_enabled": True})


def client_with(settings: Settings, server: FakeServer, dns: FakeDns) -> Iterator[ApiClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_mail_providers] = lambda: server.factory
    app.dependency_overrides[get_dns_checker] = lambda: dns
    with TestClient(app) as http:
        yield ApiClient(http)


@pytest.fixture
def ada(engine: Engine) -> uuid.UUID:
    return make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")


@pytest.fixture
def client(
    engine: Engine, ada: uuid.UUID, enabled: Settings, server: FakeServer, dns: FakeDns
) -> Iterator[ApiClient]:
    for api in client_with(enabled, server, dns):
        api.login("ada@verkies.test")
        yield api


def connect(api: ApiClient, **changes: object):  # type: ignore[no-untyped-def]
    body = {
        "address": "ada@verkies.test",
        "display_name": "Ada Admin",
        "smtp_host": "smtp.verkies.test",
        "smtp_port": 465,
        "smtp_security": "ssl",
        "imap_host": "imap.verkies.test",
        "imap_port": 993,
        "username": "ada@verkies.test",
        "password": PASSWORD,
        "dkim_selector": "google",
        "sending_enabled": True,
        **changes,
    }
    return api.send("PUT", "/mailbox", json=body)


def test_connecting_a_mailbox_encrypts_its_password_and_checks_dns(
    engine: Engine, client: ApiClient, server: FakeServer, dns: FakeDns
) -> None:
    assert client.get("/mailbox").json() == {"mailbox": None, "sending_allowed_by_admin": True}
    assert connect(client, password=None).status_code == 422  # first connect needs it

    saved = connect(client)
    assert saved.status_code == 200, saved.text
    box = saved.json()
    assert box["status"] == "connected" and box["dns_ok"] and box["has_password"]
    assert "password" not in box and PASSWORD not in saved.text
    assert server.logins[-1].password == PASSWORD  # decrypted only to sign in
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT secret_encrypted FROM mailboxes")).scalar_one()
    assert stored and PASSWORD not in stored

    # A bad password marks it failing, with the server's reason; the old password is kept.
    server.refuse_login = True
    failing = connect(client, password="wrong").json()  # noqa: S106
    assert failing["status"] == "failing" and "refused the sign-in" in failing["last_error"]
    server.refuse_login = False
    assert connect(client, password=None).json()["status"] == "connected"

    # A missing DMARC record is reported with what to add, and sending is not allowed.
    del dns.records["_dmarc.verkies.test"]
    checked = client.send("POST", "/mailbox/check").json()
    assert not checked["dns_ok"]
    assert "_dmarc.verkies.test" in checked["dns_checks"]["dmarc"]["advice"]

    assert client.send("DELETE", "/mailbox").status_code == 204
    gone = client.get("/mailbox").json()["mailbox"]
    assert (
        gone["status"] == "disconnected"
        and not gone["has_password"]
        and not gone["sending_enabled"]
    )


def test_nothing_is_sent_without_explicit_configuration(
    engine: Engine, ada: uuid.UUID, server: FakeServer, dns: FakeDns
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=ada)
    jane = contact(engine, acme, "Jane Doe", "jane@acme.test")
    off = get_settings().model_copy(update={"email_sending_enabled": False})
    for api in client_with(off, server, dns):
        api.login("ada@verkies.test")
        connect(api)
        checks = api.get(f"/email/preflight?contact_id={jane}").json()
        assert not checks["ok"]
        failed = {c["key"] for c in checks["checks"] if not c["ok"]}
        assert failed == {"sending_enabled"}
        sent = api.send(
            "POST", "/email/send", json={"contact_id": jane, "subject": "Hi", "body": "Hello"}
        )
        assert sent.status_code == 422 and sent.json()["error"]["code"] == "send_blocked"
        assert "VROS_EMAIL_SENDING_ENABLED" in sent.json()["error"]["details"]["failed"][0]
        connect(api, sending_enabled=False)
    assert server.sent == []


def test_every_pre_send_check(
    engine: Engine, client: ApiClient, ada: uuid.UUID, dns: FakeDns
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=ada)
    jane = contact(engine, acme, "Jane Doe", "jane@acme.test")

    def failed(contact_id: str) -> set[str]:
        body = client.get(f"/email/preflight?contact_id={contact_id}").json()
        return {c["key"] for c in body["checks"] if not c["ok"]}

    assert failed(jane) == {"mailbox", "mailbox_sending", "sender_dns"}  # nothing connected yet
    connect(client)
    assert failed(jane) == set()

    nobody = contact(engine, acme, "No Email")
    assert failed(nobody) == {"recipient"}

    dns.no_mx.add("acme.test")
    assert failed(jane) == {"recipient_mx"}
    dns.no_mx.clear()

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO suppressions (id, kind, value, reason) VALUES"
                " (gen_random_uuid(), 'domain', 'acme.test', 'Asked us to stop')"
            )
        )
    assert failed(jane) == {"not_suppressed"}
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM suppressions"))

    # A colleague called her last week.
    make_user(engine, "sam@verkies.test", ["admin"], name="Sam Seller")
    sam = ApiClient(client.http)  # same app, switch identity
    sam.login("sam@verkies.test")
    log(sam, acme, kind="call", call_outcome="connected", contact_id=jane, summary="Intro.")
    client.login("ada@verkies.test")
    assert failed(jane) == {"no_colleague_contact"}

    us = account(engine, "Globex Inc", domain="globex.test", owner=ada)
    with engine.begin() as conn:
        conn.execute(text("UPDATE accounts SET hq_country = 'US' WHERE id = :a"), {"a": us})
    hank = contact(engine, us, "Hank Scorpio", "hank@globex.test")
    assert failed(hank) == {"postal_address"}

    rival = account(engine, "Rival Agency", domain="rival.test", owner=ada, kind="competitor")
    assert "not_competitor" in failed(contact(engine, rival, "Rita", "rita@rival.test"))

    connect(client, daily_cap=1)
    beth = contact(engine, acme, "Beth Jones", "beth@acme.test")
    assert (
        client.send(
            "POST", "/email/send", json={"contact_id": beth, "subject": "Hi", "body": "Hello"}
        ).status_code
        == 201
    )
    assert failed(beth) == {"daily_cap"}


def test_sending_an_email(
    engine: Engine, client: ApiClient, ada: uuid.UUID, server: FakeServer
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=ada)
    jane = contact(engine, acme, "Jane Doe", "jane@acme.test")
    opp = opportunity(engine, acme, "client_portal")
    deal = client.send("POST", "/deals", json={"opportunity_id": str(opp)}).json()
    connect(client)

    sent = client.send(
        "POST",
        "/email/send",
        json={
            "contact_id": jane,
            "deal_id": deal["id"],
            "subject": "A client portal for Acme",
            "body": "Hi Jane,\n\nWould a portal help your intake?\n\nAda",
        },
    )
    assert sent.status_code == 201, sent.text
    email = sent.json()
    assert email["status"] == "sent" and email["direction"] == "outbound"
    assert email["deal_id"] == deal["id"] and email["opportunity_id"] == str(opp)

    mime = server.sent[0]
    assert (
        mime["To"] == "Jane Doe <jane@acme.test>" and mime["From"] == "Ada Admin <ada@verkies.test>"
    )
    body = mime.get_content()
    assert "Would a portal help" in body
    assert "Ada Admin, Verkies" in body and 'reply "no thanks"' in body  # §12B.7

    timeline = [e["summary"] for e in client.get(f"/accounts/{acme}/timeline").json()]
    assert any(s.startswith("Email to Jane Doe: A client portal for Acme") for s in timeline)
    rel = next(c for c in client.get(f"/accounts/{acme}").json()["contacts"] if c["id"] == jane)
    assert rel["relationship"]["response_status"] == "no_reply"
    assert [m["subject"] for m in client.get(f"/email/messages?deal_id={deal['id']}").json()] == [
        "A client portal for Acme"
    ]

    # A server failure is recorded as failed, with no activity, and the user is told why.
    server.refuse_send = True
    failed = client.send(
        "POST", "/email/send", json={"contact_id": jane, "subject": "Again", "body": "Hi"}
    )
    assert failed.status_code == 422 and failed.json()["error"]["code"] == "send_failed"
    statuses = {
        m["subject"]: m["status"] for m in client.get(f"/email/messages?contact_id={jane}").json()
    }
    assert statuses == {"A client portal for Acme": "sent", "Again": "failed"}
    assert len(client.get(f"/activities?contact_id={jane}").json()) == 1


def inbound(
    uid: int, sender: str, body: str, *, reply_to: str | None = None, mid: str | None = None
) -> Inbound:
    return Inbound(
        uid=uid,
        message_id=mid or f"<in-{uid}@mail.test>",
        in_reply_to=reply_to,
        references=[reply_to] if reply_to else [],
        from_address=sender,
        to_addresses=["ada@verkies.test"],
        subject="Re: A client portal for Acme",
        text=body,
        date=datetime.now(UTC),
    )


def test_reading_replies_opt_outs_and_bounces(
    engine: Engine, client: ApiClient, ada: uuid.UUID, server: FakeServer
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=ada)
    jane = contact(engine, acme, "Jane Doe", "jane@acme.test")
    bob = contact(engine, acme, "Bob Stone", "bob@acme.test")
    gone = contact(engine, acme, "Gone Person", "gone@acme.test")
    connect(client)
    first = client.send(
        "POST",
        "/email/send",
        json={"contact_id": jane, "subject": "A client portal for Acme", "body": "Hi"},
    ).json()
    to_gone = client.send(
        "POST", "/email/send", json={"contact_id": gone, "subject": "Hello", "body": "Hi"}
    ).json()
    sent_id = server.sent[0]["Message-ID"]
    gone_id = server.sent[1]["Message-ID"]

    server.inbox = [
        inbound(1, "jane@acme.test", "Happy to talk on Thursday.", reply_to=sent_id),
        inbound(2, "stranger@elsewhere.test", "Buy our widgets"),  # not a contact: ignored
        inbound(3, "bob@acme.test", "No thanks, please remove me."),  # known contact, opts out
        Inbound(
            uid=4,
            message_id="<dsn@mx.test>",
            in_reply_to=None,
            references=[],
            from_address="mailer-daemon@mx.test",
            to_addresses=["ada@verkies.test"],
            subject="Undelivered",
            text="",
            date=NOW,
            is_bounce=True,
            bounce_status="5.1.1",
            bounced_message_id=gone_id,
        ),
    ]
    result = client.send("POST", "/mailbox/sync").json()
    assert result == {"read": 4, "stored": 2, "opt_outs": 1, "bounces": 1}

    emails = {m["from_address"]: m for m in client.get(f"/email/messages?account_id={acme}").json()}
    reply = emails["jane@acme.test"]
    assert reply["direction"] == "inbound" and reply["thread_key"] == first["thread_key"]
    assert "stranger@elsewhere.test" not in emails
    assert emails["bob@acme.test"]["classification"] == "opt_out"
    statuses = {
        m["to_address"]: m["status"]
        for m in client.get(f"/email/messages?contact_id={gone}").json()
    }
    assert statuses == {"gone@acme.test": "bounced"}
    assert to_gone["status"] == "sent"

    contacts = {c["id"]: c for c in client.get(f"/accounts/{acme}").json()["contacts"]}
    assert contacts[jane]["relationship"]["response_status"] == "replied"
    with engine.connect() as conn:
        suppressed = dict(conn.execute(text("SELECT value, reason FROM suppressions")).all())
    assert set(suppressed) == {"bob@acme.test", "gone@acme.test"}
    assert suppressed["gone@acme.test"] == "Hard bounce (5.1.1)"
    blocked = client.get(f"/email/preflight?contact_id={bob}").json()
    assert not blocked["ok"]

    summaries = [e["summary"] for e in client.get(f"/accounts/{acme}/timeline").json()]
    assert (
        "Email from Jane Doe: Re: A client portal for Acme Happy to talk on Thursday." in summaries
    )
    assert any("asked not to be contacted" in s for s in summaries)
    assert any("bounced (5.1.1)" in s for s in summaries)

    # Reading again stores nothing twice.
    assert client.send("POST", "/mailbox/sync").json() == {
        "read": 0,
        "stored": 0,
        "opt_outs": 0,
        "bounces": 0,
    }


def test_emails_follow_account_visibility_and_mailboxes_are_never_shared(
    engine: Engine,
    client: ApiClient,
    ada: uuid.UUID,
    enabled: Settings,
    server: FakeServer,
    dns: FakeDns,
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=ada)
    jane = contact(engine, acme, "Jane Doe", "jane@acme.test")
    connect(client)
    client.send("POST", "/email/send", json={"contact_id": jane, "subject": "Hi", "body": "Hello"})

    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    for sam in client_with(enabled, server, dns):
        sam.login("sam@verkies.test")
        assert sam.get(f"/email/messages?account_id={acme}").json() == []
        assert sam.get(f"/email/preflight?contact_id={jane}").status_code == 404
        taken = connect(sam, display_name="Sam")
        assert taken.status_code == 422 and taken.json()["error"]["code"] == "mailbox_taken"
