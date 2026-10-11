"""Slice 3.4: parsing inbound mail, opt-outs, DNS advice, encryption at rest and the footer."""

import pytest

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.mail import crypto
from app.mail.dns_check import DnsUnavailable, all_pass, check_sender_domain
from app.mail.provider import new_text, parse_inbound
from app.mail.service import footer, is_opt_out

REPLY = b"""From: "Jane Doe" <Jane@Acme.test>
To: ada@verkies.test
Subject: Re: Your client portal
Message-ID: <reply-1@acme.test>
In-Reply-To: <sent-1@verkies.test>
References: <sent-1@verkies.test>
Date: Sun, 11 Oct 2026 09:30:00 +0100
Content-Type: text/plain; charset=utf-8

Happy to talk on Thursday at 10.

On Fri, 9 Oct 2026 at 14:00, Ada Admin <ada@verkies.test> wrote:
> Hi Jane, would a portal help your intake?
"""

BOUNCE = b"""From: Mail Delivery System <MAILER-DAEMON@mx.verkies.test>
To: ada@verkies.test
Subject: Undelivered Mail Returned to Sender
Message-ID: <dsn-1@mx.verkies.test>
Date: Sun, 11 Oct 2026 09:31:00 +0000
MIME-Version: 1.0
Content-Type: multipart/report; report-type=delivery-status; boundary="B"

--B
Content-Type: text/plain

Your message could not be delivered.
--B
Content-Type: message/delivery-status

Reporting-MTA: dns; mx.verkies.test

Final-Recipient: rfc822; gone@acme.test
Action: failed
Status: 5.1.1
--B
Content-Type: text/rfc822-headers

From: ada@verkies.test
To: gone@acme.test
Message-ID: <sent-2@verkies.test>
Subject: Hello
--B--
"""


def test_a_reply_is_parsed_and_its_quoted_history_dropped() -> None:
    item = parse_inbound(7, REPLY)
    assert item.uid == 7 and item.message_id == "<reply-1@acme.test>"
    assert item.in_reply_to == "<sent-1@verkies.test>"
    assert item.references == ["<sent-1@verkies.test>"]
    assert item.from_address == "jane@acme.test"  # compared in lower case
    assert item.text == "Happy to talk on Thursday at 10."
    assert item.date is not None and item.date.utcoffset() is not None
    assert not item.is_bounce


def test_a_hard_bounce_names_the_email_it_bounces() -> None:
    item = parse_inbound(8, BOUNCE)
    assert item.is_bounce and item.bounce_status == "5.1.1"
    assert item.bounced_message_id == "<sent-2@verkies.test>"


def test_html_only_mail_is_read_as_text() -> None:
    raw = (
        b"From: x@acme.test\nTo: ada@verkies.test\nSubject: Hi\nMessage-ID: <h@acme.test>\n"
        b"Content-Type: text/html\n\n<p>Yes, <b>interested</b>.</p>"
    )
    assert "interested" in parse_inbound(1, raw).text


@pytest.mark.parametrize(
    ("text", "opted_out"),
    [
        ("No thanks, we're sorted.", True),
        ("Please remove me from your list", True),
        ("Unsubscribe", True),
        # "Not now" is a reply to classify (slice 3.5), not a request never to be contacted.
        ("We're not interested at the moment.", False),
        ("Thanks, Thursday works!", False),
        ("Yes please, send the examples.", False),
    ],
)
def test_opt_out_replies(text: str, opted_out: bool) -> None:
    assert is_opt_out(text) is opted_out


def test_quoted_opt_out_wording_does_not_count() -> None:
    reply = new_text('Sounds good.\n\nOn Mon, Ada wrote:\n> reply "no thanks" and I won\'t...')
    assert reply == "Sounds good." and not is_opt_out(reply)


class FakeDns:
    def __init__(self, records: dict[str, list[str]], mx: list[str], fail: bool = False) -> None:
        self.records, self.mx_hosts, self.fail = records, mx, fail

    async def txt(self, name: str) -> list[str]:
        if self.fail:
            raise DnsUnavailable("timeout")
        return self.records.get(name, [])

    async def mx(self, domain: str) -> list[str]:
        if self.fail:
            raise DnsUnavailable("timeout")
        return self.mx_hosts


GOOD = {
    "verkies.test": ["v=spf1 include:_spf.google.com ~all", "google-site-verification=x"],
    "_dmarc.verkies.test": ["v=DMARC1; p=quarantine"],
    "google._domainkey.verkies.test": ["v=DKIM1; k=rsa; p=MIIBIjANBg"],
}


async def test_a_well_set_up_domain_passes_every_check() -> None:
    checks = await check_sender_domain(FakeDns(GOOD, ["mx.google.com"]), "verkies.test", "google")
    assert {k: v["status"] for k, v in checks.items()} == {
        "mx": "pass",
        "spf": "pass",
        "dkim": "pass",
        "dmarc": "pass",
    }
    assert all_pass(checks)


async def test_each_missing_record_says_what_to_add() -> None:
    bad = {"verkies.test": ["v=spf1 a +all"]}
    checks = await check_sender_domain(FakeDns(bad, []), "verkies.test", None)
    assert checks["spf"]["status"] == "fail" and "+all" in (checks["spf"]["advice"] or "")
    assert checks["dmarc"]["status"] == "fail" and "_dmarc.verkies.test" in (
        checks["dmarc"]["advice"] or ""
    )
    assert checks["dkim"]["status"] == "fail" and "selector" in (checks["dkim"]["advice"] or "")
    assert checks["mx"]["status"] == "fail"
    assert not all_pass(checks)
    two = {"verkies.test": ["v=spf1 ~all", "v=spf1 -all"]}
    assert (await check_sender_domain(FakeDns(two, ["mx"]), "verkies.test", None))["spf"][
        "advice"
    ] == "There are several SPF records. Merge them into one."


async def test_a_failed_lookup_is_unknown_and_blocks_sending() -> None:
    checks = await check_sender_domain(FakeDns({}, [], fail=True), "verkies.test", "google")
    assert {v["status"] for v in checks.values()} == {"unknown"}
    assert not all_pass(checks)


def test_passwords_are_encrypted_and_bound_to_the_secret_key() -> None:
    settings = get_settings().model_copy(update={"secret_key": None})
    token = crypto.encrypt(settings, "hunter2-but-longer")
    assert "hunter2" not in token
    assert crypto.decrypt(settings, token) == "hunter2-but-longer"
    from pydantic import SecretStr

    other = settings.model_copy(update={"secret_key": SecretStr("x" * 40)})
    with pytest.raises(ValidationFailed) as caught:
        crypto.decrypt(other, token)
    assert caught.value.code == "mailbox_reconnect"


def test_the_footer_identifies_the_sender_and_offers_an_opt_out() -> None:
    settings = get_settings().model_copy(update={"email_postal_address": "1 High St, Leeds"})
    uk = footer("Ada Admin", settings, us_recipient=False)
    assert "Ada Admin, Verkies" in uk and 'reply "no thanks"' in uk and "High St" not in uk
    assert footer("Ada Admin", settings, us_recipient=True).endswith("1 High St, Leeds")
