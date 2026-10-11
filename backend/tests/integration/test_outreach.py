"""Slice 3.5: templates, sequences, enrolling, the queue, and stopping by itself.

Nothing in these tests is sent without a person's action: every step is a request a person makes.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text

from app.config import Settings, get_settings
from app.mail.provider import Inbound
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_activities import contact, log
from tests.integration.test_email import FakeDns, FakeServer, client_with, connect
from tests.integration.test_leads import account, opportunity

pytestmark = pytest.mark.integration


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def dns() -> FakeDns:
    return FakeDns()


@pytest.fixture
def settings() -> Settings:
    return get_settings().model_copy(
        update={"email_sending_enabled": True, "linkedin_daily_limit": 1}
    )


@pytest.fixture
def ada(engine: Engine) -> uuid.UUID:
    return make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")


@pytest.fixture
def client(
    engine: Engine, ada: uuid.UUID, settings: Settings, server: FakeServer, dns: FakeDns
) -> Iterator[ApiClient]:
    for api in client_with(settings, server, dns):
        api.login("ada@verkies.test")
        yield api


def default_sequence(api: ApiClient) -> dict:  # type: ignore[type-arg]
    return next(s for s in api.get("/outreach/sequences").json() if s["name"] == "Default outreach")


def due_now(engine: Engine, enrollment_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE enrollments SET next_due_at = now() WHERE id = :e"), {"e": enrollment_id}
        )


def queue_item(api: ApiClient, enrollment_id: str) -> dict | None:  # type: ignore[type-arg]
    return next(
        (
            i
            for i in api.get("/outreach/queue").json()["items"]
            if i["enrollment_id"] == enrollment_id
        ),
        None,
    )


def test_the_default_sequence_and_who_may_change_it(
    engine: Engine, client: ApiClient, settings: Settings, server: FakeServer, dns: FakeDns
) -> None:
    sequence = default_sequence(client)
    assert [(s["channel"], s["delay_days"]) for s in sequence["steps"]] == [
        ("email", 0),
        ("linkedin", 2),
        ("email", 2),
        ("call", 3),
        ("email", 4),
    ]
    templates = {t["name"]: t for t in client.get("/outreach/templates").json()}
    assert templates["First email"]["subject"] == "{company} and {service}"
    assert templates["Follow-up email"]["subject"] is None  # replies in the thread

    bad = client.send(
        "POST",
        "/outreach/templates",
        json={"name": "Bad", "channel": "email", "subject": "Hi", "body": "Hello {nickname}"},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unknown_variable"
    made = client.send(
        "POST",
        "/outreach/templates",
        json={
            "name": "Short",
            "channel": "linkedin",
            "subject": "ignored",
            "body": "Hi {first_name}",
        },
    )
    assert made.status_code == 201 and made.json()["subject"] is None

    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    for sam in client_with(settings, server, dns):
        sam.login("sam@verkies.test")
        assert sam.get("/outreach/sequences").status_code == 200  # salespeople use them
        denied = sam.send(
            "POST",
            "/outreach/templates",
            json={"name": "Mine", "channel": "email", "subject": "Hi", "body": "Hello"},
        )
        assert denied.status_code == 403


def test_enrolling_is_an_approval_and_respects_suppression(
    engine: Engine, client: ApiClient, ada: uuid.UUID
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=ada)
    jane = contact(engine, acme, "Jane Doe", "jane@acme.test")
    sequence = default_sequence(client)

    preview = client.get(f"/outreach/sequences/{sequence['id']}/preview?contact_id={jane}").json()
    first = preview["steps"][0]["draft"]
    assert first["subject"] == "Acme Legal and {service}"  # no lead brief: left for a person
    assert first["body"].startswith("Hi Jane,")
    assert set(first["missing"]) == {"service", "why_now", "problem", "similar_project"}
    assert len(preview["steps"]) == 5
    follow_up = preview["steps"][2]["draft"]  # shown as the reply it will be
    assert follow_up["subject"] == "Re: Acme Legal and {service}"
    assert "subject" not in follow_up["missing"] and "service" in follow_up["missing"]

    enrolled = client.send(
        "POST", "/outreach/enrollments", json={"sequence_id": sequence["id"], "contact_id": jane}
    )
    assert enrolled.status_code == 201, enrolled.text
    body = enrolled.json()
    assert body["status"] == "active" and body["next_position"] == 0 and body["approved_at"]
    again = client.send(
        "POST", "/outreach/enrollments", json={"sequence_id": sequence["id"], "contact_id": jane}
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_enrolled"

    no_email = contact(engine, acme, "No Email")
    assert (
        client.send(
            "POST",
            "/outreach/enrollments",
            json={"sequence_id": sequence["id"], "contact_id": no_email},
        ).status_code
        == 422
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO suppressions (id, kind, value, reason) VALUES"
                " (gen_random_uuid(), 'email', 'bob@acme.test', 'Asked us to stop')"
            )
        )
    bob = contact(engine, acme, "Bob Stone", "bob@acme.test")
    refused = client.send(
        "POST", "/outreach/enrollments", json={"sequence_id": sequence["id"], "contact_id": bob}
    )
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "suppressed"

    rival = account(engine, "Rival", domain="rival.test", owner=ada, kind="competitor")
    rita = contact(engine, rival, "Rita", "rita@rival.test")
    assert (
        client.send(
            "POST",
            "/outreach/enrollments",
            json={"sequence_id": sequence["id"], "contact_id": rita},
        ).json()["error"]["code"]
        == "competitor"
    )
    timeline = [e["summary"] for e in client.get(f"/accounts/{acme}/timeline").json()]
    assert any(s.startswith("Jane Doe enrolled in Default outreach") for s in timeline)


def test_working_through_the_queue(
    engine: Engine, client: ApiClient, ada: uuid.UUID, server: FakeServer
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=ada)
    jane = contact(engine, acme, "Jane Doe", "jane@acme.test")
    connect(client)
    sequence = default_sequence(client)
    eid = client.send(
        "POST", "/outreach/enrollments", json={"sequence_id": sequence["id"], "contact_id": jane}
    ).json()["id"]

    item = queue_item(client, eid)
    assert item is not None and item["channel"] == "email" and item["position"] == 0
    unfilled = client.send(
        "POST",
        f"/outreach/enrollments/{eid}/steps",
        json={
            "action": "email",
            "subject": item["draft"]["subject"],
            "body": item["draft"]["body"],
        },
    )
    assert unfilled.status_code == 422 and unfilled.json()["error"]["code"] == "unfilled_variables"
    assert server.sent == []  # nothing goes out until the person finishes the text

    sent = client.send(
        "POST",
        f"/outreach/enrollments/{eid}/steps",
        json={
            "action": "email",
            "subject": "Acme Legal and a client portal",
            "body": "Hi Jane,\n\nWould a portal help your intake?\n\nAda",
        },
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["next_position"] == 1 and sent.json()["history"][0]["outcome"] == "sent"
    first_id = server.sent[0]["Message-ID"]
    assert queue_item(client, eid) is None  # the LinkedIn step is due in two days
    early = client.send(
        "POST", f"/outreach/enrollments/{eid}/steps", json={"action": "linkedin", "outcome": "sent"}
    )
    assert early.status_code == 409 and early.json()["error"]["code"] == "not_due"

    # LinkedIn: the person sends the note in their own browser and records it.
    due_now(engine, eid)
    item = queue_item(client, eid)
    assert item["channel"] == "linkedin" and item["linkedin_is_search"]
    assert item["linkedin_url"].startswith("https://www.linkedin.com/search/results/people/")
    wrong_link = client.send(
        "POST",
        f"/outreach/enrollments/{eid}/steps",
        json={"action": "linkedin", "outcome": "sent", "profile_url": "https://evil.test/x"},
    )
    assert wrong_link.status_code == 422
    noted = client.send(
        "POST",
        f"/outreach/enrollments/{eid}/steps",
        json={
            "action": "linkedin",
            "outcome": "sent",
            "body": item["draft"]["body"],
            "profile_url": "https://www.linkedin.com/in/jane-doe",
        },
    ).json()
    assert noted["next_position"] == 2
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT linkedin_url, linkedin_connection_status FROM contacts WHERE id = :c"),
            {"c": jane},
        ).one()
    assert row == ("https://www.linkedin.com/in/jane-doe", "pending")

    # The follow-up email replies in the same thread.
    due_now(engine, eid)
    item = queue_item(client, eid)
    assert item["draft"]["subject"] == "Re: Acme Legal and a client portal"
    assert item["draft"]["reply_to_id"] is not None
    client.send(
        "POST",
        f"/outreach/enrollments/{eid}/steps",
        json={
            "action": "email",
            "subject": item["draft"]["subject"],
            "body": "Hi Jane, following up.",
        },
    )
    assert server.sent[1]["In-Reply-To"] == first_id

    # The call is skipped and the final note sent: the sequence is complete.
    due_now(engine, eid)
    client.send("POST", f"/outreach/enrollments/{eid}/steps", json={"action": "skip"})
    due_now(engine, eid)
    done = client.send(
        "POST",
        f"/outreach/enrollments/{eid}/steps",
        json={
            "action": "email",
            "subject": "Re: Acme Legal and a client portal",
            "body": "Last note.",
        },
    ).json()
    assert done["status"] == "completed"
    assert [h["outcome"] for h in done["history"]] == ["sent", "sent", "sent", "skipped", "sent"]
    timeline = [e["summary"] for e in client.get(f"/accounts/{acme}/timeline").json()]
    assert "Sequence finished: Jane Doe in Default outreach." in timeline


def test_the_linkedin_daily_limit(engine: Engine, client: ApiClient, ada: uuid.UUID) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=ada)
    note = next(t for t in client.get("/outreach/templates").json() if t["channel"] == "linkedin")
    linkedin_first = client.send(
        "POST",
        "/outreach/sequences",
        json={
            "name": "LinkedIn only",
            "steps": [{"channel": "linkedin", "delay_days": 0, "template_id": note["id"]}],
        },
    ).json()
    ids = []
    for name in ("Jane Doe", "Bob Stone"):
        person = contact(engine, acme, name, f"{name.split()[0].lower()}@acme.test")
        ids.append(
            client.send(
                "POST",
                "/outreach/enrollments",
                json={"sequence_id": linkedin_first["id"], "contact_id": person},
            ).json()["id"]
        )
    first = client.send(
        "POST",
        f"/outreach/enrollments/{ids[0]}/steps",
        json={"action": "linkedin", "outcome": "sent"},
    )
    assert first.json()["status"] == "completed"
    limited = client.send(
        "POST",
        f"/outreach/enrollments/{ids[1]}/steps",
        json={"action": "linkedin", "outcome": "sent"},
    )
    assert limited.status_code == 422 and limited.json()["error"]["code"] == "linkedin_limit"
    assert client.get("/outreach/queue").json()["linkedin"]["blocked"]
    # Recording that they were already connected is not a new note, so it is allowed.
    assert (
        client.send(
            "POST",
            f"/outreach/enrollments/{ids[1]}/steps",
            json={"action": "linkedin", "outcome": "already_connected"},
        ).status_code
        == 200
    )


def test_a_sequence_stops_by_itself(
    engine: Engine, client: ApiClient, ada: uuid.UUID, server: FakeServer
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=ada)
    connect(client)
    sequence = default_sequence(client)

    def enroll(name: str, at: uuid.UUID = acme) -> tuple[str, str]:
        person = contact(engine, at, name, f"{name.split()[0].lower()}@acme.test")
        eid = client.send(
            "POST",
            "/outreach/enrollments",
            json={"sequence_id": sequence["id"], "contact_id": person},
        ).json()["id"]
        return person, eid

    def status(eid: str, person: str) -> tuple[str, str | None]:
        found = next(
            e
            for e in client.get(f"/outreach/enrollments?contact_id={person}").json()
            if e["id"] == eid
        )
        return found["status"], found["stop_reason"]

    # A reply to the first email stops the sequence; an automatic reply does not.
    jane, jane_e = enroll("Jane Doe")
    client.send(
        "POST",
        f"/outreach/enrollments/{jane_e}/steps",
        json={"action": "email", "subject": "Hello", "body": "Hi Jane"},
    )
    sent_id = server.sent[0]["Message-ID"]
    now = datetime.now(UTC)
    away = Inbound(
        1,
        "<ooo@acme.test>",
        sent_id,
        [sent_id],
        "jane@acme.test",
        ["ada@verkies.test"],
        "Out of office",
        "Back Monday.",
        now,
        auto_reply=True,
    )
    server.inbox = [away]
    client.send("POST", "/mailbox/sync")
    assert status(jane_e, jane) == ("active", None)
    emails = {m["subject"]: m for m in client.get(f"/email/messages?contact_id={jane}").json()}
    assert emails["Out of office"]["classification"] == "out_of_office"
    server.inbox = [
        away,
        Inbound(
            2,
            "<re@acme.test>",
            sent_id,
            [sent_id],
            "jane@acme.test",
            ["ada@verkies.test"],
            "Re: Hello",
            "Yes, let's talk.",
            now,
        ),
    ]
    client.send("POST", "/mailbox/sync")
    assert status(jane_e, jane) == ("stopped", "They replied or spoke with you")

    # A logged meeting stops it.
    bob, bob_e = enroll("Bob Stone")
    log(client, acme, kind="meeting", contact_id=bob, summary="Discovery.")
    assert status(bob_e, bob) == ("stopped", "A meeting was logged")

    # Opening a deal on the account stops the rest.
    cara, cara_e = enroll("Cara Lee")
    client.send("POST", "/deals", json={"opportunity_id": str(opportunity(engine, acme, "crm"))})
    assert status(cara_e, cara) == ("stopped", "A deal was opened")

    # A suppression (an opt-out, a bounce) stops it, and the wrong person ends it.
    # (on another account, which has no deal)
    globex = account(engine, "Globex", domain="globex.test", owner=ada)
    dan, dan_e = enroll("Dan Fox", globex)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO suppressions (id, kind, value, reason) VALUES"
                " (gen_random_uuid(), 'email', 'dan@acme.test', 'Opted out')"
            )
        )
    assert status(dan_e, dan)[0] == "stopped"
    _eve, eve_e = enroll("Eve Hart", globex)
    due_now(engine, eve_e)
    client.send("POST", f"/outreach/enrollments/{eve_e}/steps", json={"action": "skip"})
    due_now(engine, eve_e)
    ended = client.send(
        "POST",
        f"/outreach/enrollments/{eve_e}/steps",
        json={"action": "linkedin", "outcome": "wrong_person"},
    ).json()
    assert (ended["status"], ended["stop_reason"]) == ("stopped", "Wrong person")
    stopped = client.send("POST", f"/outreach/enrollments/{eve_e}/steps", json={"action": "skip"})
    assert stopped.status_code == 409 and stopped.json()["error"]["code"] == "ended"


def test_only_the_owner_works_an_enrollment(
    engine: Engine,
    client: ApiClient,
    ada: uuid.UUID,
    settings: Settings,
    server: FakeServer,
    dns: FakeDns,
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test")  # unowned: everyone can see it
    jane = contact(engine, acme, "Jane Doe", "jane@acme.test")
    eid = client.send(
        "POST",
        "/outreach/enrollments",
        json={"sequence_id": default_sequence(client)["id"], "contact_id": jane},
    ).json()["id"]
    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    for sam in client_with(settings, server, dns):
        sam.login("sam@verkies.test")
        assert sam.get("/outreach/queue").json()["items"] == []
        assert (
            sam.send(
                "POST", f"/outreach/enrollments/{eid}/steps", json={"action": "skip"}
            ).status_code
            == 403
        )
