"""Slice 3.2: logging activities, editing contacts, relationship tracking and follow-up flags."""

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.accounts.models import Account
from app.config import get_settings
from app.core.enums import ActivityDirection
from app.crm.activities import Relationship, account_relationships, relationship
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_deals import admin, stages  # noqa: F401 - fixture
from tests.integration.test_leads import account, opportunity

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


def contact(engine: Engine, account_id: uuid.UUID, name: str, email: str | None = None) -> str:
    contact_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO contacts (id, account_id, name, email, source, collected_at,"
                " confidence, verification_status, lawful_basis)"
                " VALUES (:id, :a, :n, :e, 'website', now(), 0.8, 'unverified',"
                " 'b2b_legitimate_interest')"
            ),
            {"id": contact_id, "a": account_id, "n": name, "e": email},
        )
    return str(contact_id)


def log(api: ApiClient, account_id: uuid.UUID, **body: object):  # type: ignore[no-untyped-def]
    return api.send("POST", "/activities", json={"account_id": str(account_id), **body})


def backdate(engine: Engine, sql: str, **params: object) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql), params)


def test_logging_a_call_with_a_follow_up_on_a_deal(
    engine: Engine,
    api: ApiClient,
    admin: uuid.UUID,  # noqa: F811
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin)
    opp = opportunity(engine, acme, "crm")
    jane = contact(engine, acme, "Jane Doe", "jane@acme.test")
    deal = api.send("POST", "/deals", json={"opportunity_id": str(opp)}).json()
    when = (NOW - timedelta(hours=2)).isoformat()

    logged = log(
        api,
        acme,
        kind="call",
        call_outcome="no_answer",
        contact_id=jane,
        deal_id=deal["id"],
        occurred_at=when,
        summary="Rang about the proposal, went to reception.",
        follow_up={"title": "Call Jane again", "due_at": (NOW + timedelta(days=2)).isoformat()},
    )
    assert logged.status_code == 201, logged.text
    body = logged.json()
    assert body["kind"] == "call" and body["direction"] == "outbound"
    assert body["call_outcome"] == "no_answer"
    assert body["contact"] == {"id": jane, "name": "Jane Doe"}
    assert body["deal_id"] == deal["id"] and body["opportunity_id"] == str(opp)
    assert body["logged_by"]["name"] == "Ada Admin"

    # The follow-up became the deal's next task, owned by whoever logged the call.
    board = api.get(f"/deals/{deal['id']}").json()
    assert board["next_task"]["title"] == "Call Jane again"
    assert board["last_activity_at"] is not None
    with engine.connect() as conn:
        task_contact = conn.execute(
            text("SELECT contact_id FROM tasks WHERE title = 'Call Jane again'")
        ).scalar_one()
    assert str(task_contact) == jane

    timeline = api.get(f"/accounts/{acme}/timeline").json()
    call = next(e for e in timeline if e["event_type"] == "activity.call")
    assert call["summary"].startswith("Call with Jane Doe, no answer: Rang about")
    assert call["occurred_at"][:16] == when[:16]  # placed when it happened, not when logged
    audit = api.get(f"/accounts/{acme}/audit").json()
    assert any(a["action"] == "activity.logged" for a in audit)

    for query in (f"contact_id={jane}", f"deal_id={deal['id']}", f"account_id={acme}"):
        assert [a["id"] for a in api.get(f"/activities?{query}").json()] == [body["id"]]

    # Jane picks up the second time: she has now replied.
    log(api, acme, kind="call", call_outcome="connected", contact_id=jane, summary="Spoke.")
    people = api.get(f"/accounts/{acme}").json()
    rel = next(c for c in people["contacts"] if c["id"] == jane)["relationship"]
    assert rel["interactions"] == 2 and rel["response_status"] == "replied"
    assert rel["attempts_since_reply"] == 0 and rel["days_since_contact"] == 0
    assert people["relationship"]["interactions"] == 2
    assert people["last_activity_at"] is not None


def test_notes_and_messages_and_the_relationship_they_build(
    engine: Engine,
    api: ApiClient,
    admin: uuid.UUID,  # noqa: F811
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin)
    jane = contact(engine, acme, "Jane Doe")
    note = log(api, acme, kind="note", contact_id=jane, summary="Prefers email.")
    assert note.status_code == 201 and note.json()["direction"] == "internal"
    sent = log(
        api,
        acme,
        kind="message",
        message_channel="linkedin",
        contact_id=jane,
        summary="Connection note sent.",
    )
    assert sent.json()["channel"] == "linkedin" and sent.json()["direction"] == "outbound"

    rel = api.get(f"/accounts/{acme}").json()["contacts"][0]["relationship"]
    assert rel["response_status"] == "no_reply" and rel["attempts_since_reply"] == 1
    assert rel["interactions"] == 1  # the note is not an interaction

    received = log(
        api,
        acme,
        kind="message",
        message_channel="linkedin",
        received=True,
        contact_id=jane,
        summary="Happy to talk next week.",
    )
    assert received.json()["direction"] == "inbound"
    rel = api.get(f"/accounts/{acme}").json()["contacts"][0]["relationship"]
    assert rel["response_status"] == "replied"

    summaries = [e["summary"] for e in api.get(f"/accounts/{acme}/timeline").json()]
    assert "LinkedIn message from Jane Doe: Happy to talk next week." in summaries
    assert "Note about Jane Doe: Prefers email." in summaries


def test_what_an_activity_can_be_logged_against(
    engine: Engine,
    api: ApiClient,
    admin: uuid.UUID,  # noqa: F811
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin)
    other = account(engine, "Other Ltd", domain="other.test", owner=admin)
    stranger = contact(engine, other, "Sam Stranger")
    opp_a = opportunity(engine, acme, "crm")
    opp_b = opportunity(engine, acme, "seo")
    deal = api.send("POST", "/deals", json={"opportunity_id": str(opp_a)}).json()

    future = log(
        api, acme, kind="note", summary="x", occurred_at=(NOW + timedelta(hours=1)).isoformat()
    )
    assert future.status_code == 422 and future.json()["error"]["code"] == "occurred_in_future"
    assert log(api, acme, kind="note", contact_id=stranger, summary="x").status_code == 422
    assert (
        log(
            api, acme, kind="note", deal_id=deal["id"], opportunity_id=str(opp_b), summary="x"
        ).status_code
        == 422
    )
    no_outcome = log(api, acme, kind="call", summary="x")
    assert no_outcome.json()["error"]["code"] == "call_outcome_required"
    assert log(api, acme, kind="note", summary="   ").status_code == 422
    assert api.get("/activities").status_code == 422  # say whose activities


def test_adding_and_editing_contacts(
    engine: Engine,
    api: ApiClient,
    admin: uuid.UUID,  # noqa: F811
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin)
    added = api.send(
        "POST",
        f"/accounts/{acme}/contacts",
        json={
            "name": " Jane Doe ",
            "title": "COO",
            "email": "Jane@Acme.test",
            "decision_maker_role": "economic_buyer",
            "linkedin_url": "https://www.linkedin.com/in/jane-doe",
        },
    )
    assert added.status_code == 201, added.text
    jane = added.json()
    assert jane["name"] == "Jane Doe" and jane["email"] == "jane@acme.test"
    assert jane["source"] == "manual" and jane["verification_status"] == "unverified"
    assert jane["relationship"]["response_status"] == "not_contacted"

    duplicate = api.send(
        "POST", f"/accounts/{acme}/contacts", json={"name": "J Doe", "email": "jane@acme.test"}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"]["contact_id"] == jane["id"]

    backdate(
        engine,
        "INSERT INTO suppressions (id, kind, value, reason)"
        " VALUES (gen_random_uuid(), 'domain', 'optedout.test', 'Asked not to be contacted')",
    )
    suppressed = api.send(
        "POST",
        f"/accounts/{acme}/contacts",
        json={"name": "Opted Out", "email": "someone@optedout.test"},
    )
    assert suppressed.status_code == 422 and suppressed.json()["error"]["code"] == "suppressed"

    bad = api.send("POST", f"/accounts/{acme}/contacts", json={"name": "X", "email": "nope"})
    assert bad.status_code == 422

    edited = api.send(
        "PATCH",
        f"/contacts/{jane['id']}",
        json={"title": "Chief Operating Officer", "verification_status": "verified"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Chief Operating Officer"
    assert edited.json()["verification_status"] == "verified"
    assert api.send("PATCH", f"/contacts/{jane['id']}", json={}).status_code == 422
    assert (
        api.send("PATCH", f"/contacts/{jane['id']}", json={"verification_status": None}).status_code
        == 422
    )

    actions = [a["action"] for a in api.get(f"/accounts/{acme}/audit").json()]
    assert "contact.created" in actions and "contact.updated" in actions
    summaries = [e["summary"] for e in api.get(f"/accounts/{acme}/timeline").json()]
    assert "Contact added: Jane Doe, COO." in summaries


def test_follow_up_flags_at_their_boundaries(
    engine: Engine,
    api: ApiClient,
    admin: uuid.UUID,  # noqa: F811
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin)

    # Opportunities with no deal: stale after 14 quiet days.
    stale = opportunity(engine, acme, "crm")
    fresh = opportunity(engine, acme, "seo")
    revived = opportunity(engine, acme, "website_rebuild")
    for opp, days in ((stale, 15), (fresh, 13), (revived, 40)):
        backdate(
            engine,
            "UPDATE opportunities SET created_at = :t WHERE id = :o",
            t=NOW - timedelta(days=days),
            o=opp,
        )
    log(api, acme, kind="note", opportunity_id=str(revived), summary="Still interested.")

    # Deals: inactive after 21 days without activity or a stage move.
    quiet_opp, busy_opp, won_opp = (
        opportunity(engine, acme, "workflow_automation"),
        opportunity(engine, acme, "mobile_application"),
        opportunity(engine, acme, "client_portal"),
    )
    quiet = api.send("POST", "/deals", json={"opportunity_id": str(quiet_opp)}).json()
    busy = api.send("POST", "/deals", json={"opportunity_id": str(busy_opp)}).json()
    won = api.send("POST", "/deals", json={"opportunity_id": str(won_opp)}).json()
    api.send(
        "POST", f"/deals/{won['id']}/move", json={"stage_id": stages(api, "new_business")["won"]}
    )
    for deal_id, days in ((quiet["id"], 22), (busy["id"], 30), (won["id"], 60)):
        backdate(
            engine,
            "UPDATE deals SET stage_entered_at = :t WHERE id = :d",
            t=NOW - timedelta(days=days),
            d=deal_id,
        )
    log(api, acme, kind="meeting", deal_id=busy["id"], summary="Workshop.")

    # Tasks: overdue once the due date has passed.
    for title, due in (("Chase the proposal", -1), ("Send the deck", 1)):
        api.send(
            "POST",
            "/tasks",
            json={
                "account_id": str(acme),
                "title": title,
                "owner_id": str(admin),
                "due_at": (NOW + timedelta(days=due)).isoformat(),
            },
        )

    body = api.get("/follow-ups").json()
    assert body["stale_opportunity_days"] == 14 and body["inactive_deal_days"] == 21
    flagged = {(f["kind"], f["ref_id"]) for f in body["flags"]}
    by_kind = {k: {r for kind, r in flagged if kind == k} for k in body["counts"]}

    assert by_kind["stale_opportunity"] == {str(stale)}
    assert by_kind["inactive_deal"] == {quiet["id"]}
    overdue = [f for f in body["flags"] if f["kind"] == "overdue_follow_up"]
    assert [f["title"] for f in overdue] == ["Chase the proposal"]
    assert overdue[0]["detail"] == "Overdue by 1 day" and overdue[0]["owner"]["id"] == str(admin)
    # The won deal's opportunity needs no next action; the open ones without a task do.
    assert str(won_opp) not in by_kind["no_next_action"]
    assert {str(stale), str(fresh), str(quiet_opp)} <= by_kind["no_next_action"]
    assert body["counts"]["inactive_deal"] == 1

    deal = api.get(f"/deals/{quiet['id']}").json()
    assert "inactive for 22 days" in deal["requires_attention"]
    assert not any(
        r.startswith("inactive")
        for r in api.get(f"/deals/{busy['id']}").json()["requires_attention"]
    )
    opps = {o["id"]: o for o in api.get(f"/accounts/{acme}").json()["opportunities"]}
    assert opps[str(won_opp)]["requires_attention"] == []


def test_mine_and_who_may_see_what(
    engine: Engine,
    api: ApiClient,
    make_api,  # type: ignore[no-untyped-def]
    admin: uuid.UUID,  # noqa: F811
) -> None:
    sam = make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    ours = account(engine, "Ours Ltd", domain="ours.test", owner=admin)
    sams = account(engine, "Sams Ltd", domain="sams.test", owner=sam)
    for acct, owner in ((ours, admin), (sams, sam)):
        api.send(
            "POST",
            "/tasks",
            json={
                "account_id": str(acct),
                "title": f"Overdue for {acct}",
                "owner_id": str(owner),
                "due_at": (NOW - timedelta(days=3)).isoformat(),
            },
        )
    mine = api.get("/follow-ups?mine=true").json()["flags"]
    assert {f["account_id"] for f in mine} == {str(ours)}
    assert {f["account_id"] for f in api.get("/follow-ups").json()["flags"]} == {
        str(ours),
        str(sams),
    }

    seller = make_api()
    seller.login("sam@verkies.test")
    seen = {f["account_id"] for f in seller.get("/follow-ups").json()["flags"]}
    assert seen == {str(sams)}  # read_own: never someone else's account
    assert log(seller, ours, kind="note", summary="x").status_code == 404
    assert seller.get(f"/activities?account_id={ours}").json() == []
    assert seller.send("POST", f"/accounts/{ours}/contacts", json={"name": "X"}).status_code == 404
    assert log(seller, sams, kind="note", summary="Mine.").status_code == 201


def test_follow_ups_are_capped_but_counted_exactly(engine: Engine, api: ApiClient) -> None:
    """Slice 7.5: each kind returns at most `limit` flags, most urgent first, while `counts`
    says how many there are, so the list stays fast however many exist."""
    owner = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    acme = account(engine, "Acme Legal", domain="acme.test", owner=owner)
    with engine.begin() as conn:
        for days in (3, 9, 5):
            conn.execute(
                text(
                    "INSERT INTO tasks (id, account_id, title, owner_id, due_at, priority, status)"
                    " VALUES (gen_random_uuid(), :a, :t, :o, now() - make_interval(days => :d),"
                    " 'normal', 'open')"
                ),
                {"a": acme, "t": f"Overdue {days} days", "o": owner, "d": days},
            )
    body = api.get("/follow-ups", params={"limit": 2}).json()
    overdue = [f for f in body["flags"] if f["kind"] == "overdue_follow_up"]
    assert [f["title"] for f in overdue] == ["Overdue 9 days", "Overdue 5 days"]
    assert body["counts"]["overdue_follow_up"] == 3
    assert api.get("/follow-ups", params={"limit": 501}).status_code == 422


def test_the_relationship_folded_in_sql_matches_the_rules(engine: Engine) -> None:
    """Client health reads relationships for every client in one query; it must give exactly
    what folding each account's activities in Python gives, ties and notes included."""
    rng = random.Random(7)  # noqa: S311 - a repeatable mix of test data
    directions = list(ActivityDirection)
    base = NOW - timedelta(days=30)
    expected: dict[uuid.UUID, Relationship] = {}
    rows = []
    for n in range(40):
        acme = account(engine, f"Account {n}")
        touches = [
            (base + timedelta(hours=rng.randint(0, 12)), rng.choice(directions))
            for _ in range(rng.randint(0, 8))  # few hours, so moments are often shared
        ]
        expected[acme] = relationship(touches)
        rows += [{"id": uuid.uuid4(), "a": acme, "d": d.value, "at": at} for at, d in touches]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO activities (id, account_id, channel, activity_type, direction,"
                " occurred_at, summary, payload)"
                " VALUES (:id, :a, 'manual', 'note', :d, :at, 'Logged', '{}')"
            ),
            rows,
        )

    async def fold() -> dict[uuid.UUID, Relationship]:
        db_engine = create_async_engine(get_settings().database_url)
        try:
            async with async_sessionmaker(db_engine, class_=AsyncSession)() as db:
                return await account_relationships(db, select(Account.id))
        finally:
            await db_engine.dispose()

    folded = asyncio.run(fold())
    assert {a: folded.get(a) or relationship([]) for a in expected} == expected
    assert {r.response_status for r in expected.values()} == {
        "not_contacted",
        "no_reply",
        "awaiting_reply",
        "replied",
    }
