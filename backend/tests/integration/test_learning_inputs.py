"""Slice 5.1: salesperson feedback, and what was true when a deal was won or lost."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text

from app.cli import main as cli
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_deals import stages
from tests.integration.test_leads import account, opportunity, signal, snapshot

pytestmark = pytest.mark.integration


@pytest.fixture
def admin(engine: Engine, api: ApiClient) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    return user_id


def prepared(engine: Engine, owner: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """An account with everything an outcome records: (account, opportunity)."""
    acme = account(
        engine, "Acme Legal", domain="acme.test", owner=owner, industry="legal", country="GB"
    )
    opp = opportunity(engine, acme, "client_portal")
    snapshot(engine, acme)
    signal(engine, acme, owner, "developer_hiring", days_ago=20)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE accounts SET company_size_band = '11-50', source = 'csv_import'"
                " WHERE id = :a"
            ),
            {"a": acme},
        )
        conn.execute(
            text(
                "UPDATE opportunities SET service_id ="
                " (SELECT id FROM services WHERE key = 'crm_portal') WHERE id = :o"
            ),
            {"o": opp},
        )
        lead_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO leads (id, account_id, source, status, qualified_at)"
                " VALUES (:id, :a, 'url_research', 'qualified', :q)"
            ),
            {"id": lead_id, "a": acme, "q": datetime.now(UTC) - timedelta(days=40)},
        )
        conn.execute(
            text("UPDATE opportunities SET lead_id = :l WHERE id = :o"), {"l": lead_id, "o": opp}
        )
        conn.execute(
            text(
                "INSERT INTO contacts (id, account_id, name, source, collected_at, confidence,"
                " verification_status, lawful_basis, decision_maker_role) VALUES (:id, :a,"
                " 'Grace Okafor', 'manual', now(), 0.9, 'unverified', 'b2b_legitimate_interest',"
                " 'economic_buyer')"
            ),
            {"id": uuid.uuid4(), "a": acme},
        )
    return acme, opp


def test_winning_a_deal_records_what_was_true(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    acme, opp = prepared(engine, admin)
    deal = api.send("POST", "/deals", json={"opportunity_id": str(opp), "value": "30000"}).json()
    grace = api.get(f"/accounts/{acme}").json()["contacts"][0]["id"]
    logged = api.send(
        "POST",
        "/activities",
        json={
            "account_id": str(acme),
            "contact_id": grace,
            "deal_id": deal["id"],
            "kind": "meeting",
            "summary": "Scoping workshop",
        },
    )
    assert logged.status_code == 201, logged.text
    assert api.get(f"/deals/{deal['id']}/outcome").json() is None  # open: no outcome yet

    nb = stages(api, "new_business")
    api.send("POST", f"/deals/{deal['id']}/move", json={"stage_id": nb["won"]})
    o = api.get(f"/deals/{deal['id']}/outcome").json()
    assert o["outcome"] == "won" and not o["captured_late"]
    assert o["value"] == 30000 and o["currency"] == "GBP" and o["pipeline_key"] == "new_business"
    assert o["service"] == "CRM, practice systems and client portals"
    assert o["opportunity_type"] == "Client portal"
    assert (o["industry"], o["company_size_band"], o["hq_country"]) == ("legal", "11-50", "GB")
    assert o["source"] == "url_research"  # the lead's source over the account's
    assert o["buyer_role"] == "economic_buyer"
    assert o["deal_days"] == 0 and o["lead_days"] == 40
    assert [s["signal"] for s in o["signals"]] == ["developer_hiring"]
    assert o["first_scores"]["priority_score"] == 82
    assert o["first_scores"]["icp_score"] is None  # Unknown stays Unknown
    assert o["close_scores"]["priority_score"] == 82


def test_reopening_supersedes_and_losing_keeps_the_reason(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    _acme, opp = prepared(engine, admin)
    deal = api.send("POST", "/deals", json={"opportunity_id": str(opp)}).json()
    nb = stages(api, "new_business")

    api.send(
        "POST",
        f"/deals/{deal['id']}/move",
        json={"stage_id": nb["lost"], "lost_reason": "price"},
    )
    lost = api.get(f"/deals/{deal['id']}/outcome").json()
    assert lost["outcome"] == "lost" and lost["lost_reason"] == "Price" and lost["value"] is None

    api.send("POST", f"/deals/{deal['id']}/move", json={"stage_id": nb["proposal"]})
    assert api.get(f"/deals/{deal['id']}/outcome").json() is None
    api.send("POST", f"/deals/{deal['id']}/move", json={"stage_id": nb["won"]})
    assert api.get(f"/deals/{deal['id']}/outcome").json()["outcome"] == "won"
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT outcome, superseded_at IS NULL FROM deal_outcomes WHERE deal_id = :d"
                " ORDER BY recorded_at"
            ),
            {"d": deal["id"]},
        ).all()
    assert [(r[0], r[1]) for r in rows] == [("lost", False), ("won", True)]


def test_deals_closed_before_are_backfilled_as_late(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    _acme, opp = prepared(engine, admin)
    deal = api.send("POST", "/deals", json={"opportunity_id": str(opp)}).json()
    api.send(
        "POST", f"/deals/{deal['id']}/move", json={"stage_id": stages(api, "new_business")["won"]}
    )
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM deal_outcomes"))  # as if it closed before slice 5.1
    assert api.get(f"/deals/{deal['id']}/outcome").json() is None

    assert cli(["backfill-outcomes"]) == 0
    backfilled = api.get(f"/deals/{deal['id']}/outcome").json()
    assert backfilled["outcome"] == "won" and backfilled["captured_late"]
    assert cli(["backfill-outcomes"]) == 0  # nothing twice
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM deal_outcomes")).scalar_one() == 1


def test_salesperson_feedback(
    engine: Engine, api: ApiClient, admin: uuid.UUID, make_api: Callable[[], ApiClient]
) -> None:
    acme, opp = prepared(engine, admin)
    kinds = api.get("/sales-feedback/kinds").json()
    assert len(kinds) == 15 and kinds[0] == {"key": "good_lead", "label": "Good lead"}

    given = api.send(
        "POST",
        f"/accounts/{acme}/sales-feedback",
        json={"kind": "wrong_service", "opportunity_id": str(opp), "note": "They need SEO first"},
    )
    assert given.status_code == 201, given.text
    assert given.json()["label"] == "Wrong service" and given.json()["given_by"] == "Ada Admin"
    api.send("POST", f"/accounts/{acme}/sales-feedback", json={"kind": "good_lead"})
    listed = api.get(f"/accounts/{acme}/sales-feedback").json()
    assert [f["kind"] for f in listed] == ["good_lead", "wrong_service"]

    other = account(engine, "Other Co", domain="other.test", owner=admin)
    foreign = api.send(
        "POST",
        f"/accounts/{other}/sales-feedback",
        json={"kind": "opportunity_confirmed", "opportunity_id": str(opp)},
    )
    assert foreign.status_code == 422
    events = [e["summary"] for e in api.get(f"/accounts/{acme}/timeline").json()]
    assert "Feedback: Wrong service. They need SEO first" in events

    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    assert seller.get(f"/accounts/{acme}/sales-feedback").status_code == 404
    hidden = seller.send("POST", f"/accounts/{acme}/sales-feedback", json={"kind": "bad_lead"})
    assert hidden.status_code == 404
