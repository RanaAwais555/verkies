"""Slice 3.5: template variables, LinkedIn search links and automatic replies."""

from app.accounts.models import Account, Contact
from app.mail.provider import parse_inbound
from app.outreach.service import linkedin_search_url, render, unfilled, unknown_variables


def test_known_variables_are_filled_and_unknown_values_left_for_a_person() -> None:
    text, missing = render(
        "Hi {first_name}, {why_now} Regards, {sender_name}",
        {"first_name": "Jane", "why_now": None, "sender_name": "Ada"},
    )
    assert text == "Hi Jane, {why_now} Regards, Ada"
    assert missing == ["why_now"]
    assert unfilled(text) == ["why_now"]
    assert unfilled("Hi Jane, thanks.") == []


def test_braces_that_are_not_variables_are_left_alone_and_reported_on_save() -> None:
    text, missing = render("Price {in_gbp} and {first_name}", {"first_name": "Jane"})
    assert text == "Price {in_gbp} and Jane" and missing == []
    assert unknown_variables("Price {in_gbp} and {first_name}") == ["in_gbp"]
    assert unfilled(text) == []  # not a variable, so it does not block sending


def test_the_linkedin_search_is_a_link_the_person_opens() -> None:
    url = linkedin_search_url(Contact(name="Jane Doe"), Account(name="Acme & Co"))
    assert url == (
        "https://www.linkedin.com/search/results/people/?keywords=Jane%20Doe%20Acme%20%26%20Co"
    )


def test_automatic_replies_are_recognised() -> None:
    def mail(headers: str) -> bytes:
        return (
            f"From: jane@acme.test\nTo: ada@verkies.test\nMessage-ID: <a@acme.test>\n{headers}\n\n"
            "Back on Monday."
        ).encode()

    assert parse_inbound(1, mail("Subject: Out of office\n")).auto_reply
    assert parse_inbound(1, mail("Subject: Hi\nAuto-Submitted: auto-replied\n")).auto_reply
    assert parse_inbound(1, mail("Subject: Re: hello\nX-Autoreply: yes\n")).auto_reply
    assert not parse_inbound(1, mail("Subject: Re: hello\nAuto-Submitted: no\n")).auto_reply
    assert not parse_inbound(1, mail("Subject: Re: out of office plans\n")).auto_reply
