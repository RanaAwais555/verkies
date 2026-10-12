"""Slice 4.3: evidence-backed expansion suggestions for clients, and referrals."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text

from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_clients import won_deal
from tests.integration.test_leads import account

pytestmark = pytest.mark.integration


@pytest.fixture
def admin(engine: Engine, api: ApiClient) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    return user_id


def research(
    engine: Engine,
    account_id: str | uuid.UUID,
    user_id: uuid.UUID,
    findings: list[tuple[str, str]],
    *,
    finished: datetime | None = None,
) -> dict[str, str]:
    """A completed research run on the account that found these problems, each with evidence.
    Returns candidate ids by category key."""
    run_id = uuid.uuid4()
    out = {}
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO research_runs (id, input_url, normalised_domain, requested_by_id,"
                " status, review_status, retry_count, crawl_budget, possible_duplicate_of,"
                " account_id, finished_at)"
                " VALUES (:id, 'https://acme.test/', 'acme.test', :u, 'completed', 'approved', 0,"
                " '{}', '[]', :a, :f)"
            ),
            {"id": run_id, "u": user_id, "a": account_id, "f": finished or datetime.now(UTC)},
        )
        for key, problem in findings:
            candidate_id, evidence_id = uuid.uuid4(), uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO evidence (id, research_run_id, account_id, source_url,"
                    " source_domain, collected_at, evidence_type, evidence_text, content_hash,"
                    " confidence) VALUES (:id, :r, :a, :url, 'acme.test', now(), 'page_content',"
                    " :t, 'h', 0.8)"
                ),
                {
                    "id": evidence_id,
                    "r": run_id,
                    "a": account_id,
                    "url": f"https://acme.test/{key}",
                    "t": f"Seen on the site: {problem}",
                },
            )
            conn.execute(
                text(
                    "INSERT INTO opportunity_candidates (id, research_run_id, category_id, title,"
                    " problem_statement, confidence, rule_key)"
                    " SELECT :id, :r, id, :title, :p, 0.7, 'test' FROM opportunity_categories"
                    " WHERE key = :k"
                ),
                {
                    "id": candidate_id,
                    "r": run_id,
                    "title": f"{key} problem",
                    "p": problem,
                    "k": key,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO opportunity_candidate_evidence (candidate_id, evidence_id)"
                    " VALUES (:c, :e)"
                ),
                {"c": candidate_id, "e": evidence_id},
            )
            out[key] = str(candidate_id)
    return out


def test_suggestions_come_only_from_evidence(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    deal = won_deal(engine, api, admin)  # its opportunity is a CRM one
    client_id = deal["account_id"]
    api.send("POST", f"/deals/{deal['id']}/convert", json={})
    assert api.get(f"/accounts/{client_id}/expansion").json() == []  # no research, no suggestion

    found = research(
        engine,
        client_id,
        admin,
        [
            ("crm", "Enquiries are tracked in spreadsheets"),
            ("seo", "Service pages have no titles or descriptions"),
            ("client_portal", "Clients email documents back and forth"),
        ],
    )
    suggestions = api.get(f"/accounts/{client_id}/expansion").json()
    assert [s["category_key"] for s in suggestions] == ["client_portal", "seo"]  # CRM is taken
    seo = next(s for s in suggestions if s["category_key"] == "seo")
    assert seo["problem"] == "Service pages have no titles or descriptions"
    assert [e["source_url"] for e in seo["evidence"]] == ["https://acme.test/seo"]
    assert [x["name"] for x in seo["services"]] == ["SEO and content engine"]

    clients = api.get("/clients").json()
    assert clients[0]["expansion"] == ["Client portal", "SEO"]
    assert [c["name"] for c in api.get("/clients", params={"expansion": True}).json()] == [
        "Acme Legal"
    ]

    prospect = account(engine, "Prospect Co", domain="prospect.test", owner=admin)
    research(engine, prospect, admin, [("seo", "No titles")])
    assert api.get(f"/accounts/{prospect}/expansion").json() == []  # expansion is for clients
    refused = api.send("POST", f"/accounts/{prospect}/expansion/{uuid.uuid4()}/open", json={})
    assert refused.status_code == 422

    board = api.get("/reports/management").json()
    table = next(t for t in board["tables"] if t["key"] == "clients_with_expansion")
    assert table["rows"][0]["label"] == "Acme Legal" and table["rows"][0]["values"][0] == 2
    assert found["seo"]


def test_opening_and_dismissing(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    deal = won_deal(engine, api, admin)
    client_id = deal["account_id"]
    api.send("POST", f"/deals/{deal['id']}/convert", json={})
    found = research(
        engine,
        client_id,
        admin,
        [("seo", "Service pages have no titles"), ("client_portal", "Documents go by email")],
        finished=datetime.now(UTC) - timedelta(days=3),
    )

    wrong_service = api.send(
        "POST",
        f"/accounts/{client_id}/expansion/{found['seo']}/open",
        json={"service_id": str(uuid.uuid4())},
    )
    assert wrong_service.status_code == 422
    opened = api.send("POST", f"/accounts/{client_id}/expansion/{found['seo']}/open", json={})
    assert opened.status_code == 201, opened.text
    opportunity_id = opened.json()["opportunity_id"]
    acc = api.get(f"/accounts/{client_id}").json()
    opp = next(o for o in acc["opportunities"] if o["id"] == opportunity_id)
    assert opp["name"] == "Expansion: SEO for Acme Legal"
    assert opp["problem"] == "Service pages have no titles"
    assert opp["service_name"] == "SEO and content engine"  # the only service that answers it

    # The opportunity goes into the expansion pipeline, as the client's deals do.
    deal2 = api.send("POST", "/deals", json={"opportunity_id": opportunity_id}).json()
    assert deal2["pipeline_key"] == "expansion"

    again = api.send("POST", f"/accounts/{client_id}/expansion/{found['seo']}/open", json={})
    assert again.status_code == 404  # no longer a suggestion

    dismissed = api.send(
        "POST",
        f"/accounts/{client_id}/expansion/{found['client_portal']}/dismiss",
        json={"reason": "They use their insurer's portal"},
    )
    assert dismissed.status_code == 204
    assert api.get(f"/accounts/{client_id}/expansion").json() == []

    # Newer research finding the problem again brings it back.
    newer = research(engine, client_id, admin, [("client_portal", "Still emailing documents")])
    back = api.get(f"/accounts/{client_id}/expansion").json()
    assert [(s["candidate_id"], s["dismissed_before"]) for s in back] == [
        (newer["client_portal"], True)
    ]

    events = [e["summary"] for e in api.get(f"/accounts/{client_id}/timeline").json()]
    assert any(e.startswith("Expansion opportunity opened: SEO.") for e in events)
    assert (
        "Expansion suggestion dismissed: Client portal (They use their insurer's portal)." in events
    )
    audit = api.get(f"/accounts/{client_id}/audit").json()
    opened_entry = next(e for e in audit if e["action"] == "expansion.opened")
    assert len(opened_entry["new_value"]["evidence"]) == 1


def test_referrals_convert_when_a_deal_is_won(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    deal = won_deal(engine, api, admin)
    client_id = deal["account_id"]
    with engine.begin() as conn:
        contact_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO contacts (id, account_id, name, source, collected_at, confidence,"
                " verification_status, lawful_basis) VALUES (:id, :a, 'Grace Okafor', 'manual',"
                " now(), 0.9, 'unverified', 'b2b_legitimate_interest')"
            ),
            {"id": contact_id, "a": client_id},
        )

    made = api.send(
        "POST",
        "/referrals",
        json={
            "referrer_account_id": client_id,
            "referrer_contact_id": str(contact_id),
            "relationship": "Client",
            "referred_company": "Bright Dental",
            "referred_domain": "https://www.brightdental.test/about",
        },
    )
    assert made.status_code == 201, made.text
    referral = made.json()
    assert referral["referrer_name"] == "Grace Okafor, Acme Legal"
    assert referral["referred_domain"] == "brightdental.test"
    assert referral["referred_account"] is None and not referral["converted"]
    assert referral["status"] == "received"

    # The company is researched later: the referral links to it by domain.
    bright = won_deal(engine, api, admin, "Bright Dental")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE accounts SET primary_domain = 'brightdental.test' WHERE id = :a"),
            {"a": bright["account_id"]},
        )
    linked = api.get("/referrals").json()[0]
    assert linked["referred_account"] == {"id": bright["account_id"], "name": "Bright Dental"}
    assert linked["converted"] and linked["won_deals"] == 1
    assert linked["revenue"] == [{"amount": 18000.0, "currency": "GBP"}]

    # A deal won before the referral does not count.
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE deals SET closed_at = now() - interval '30 days' WHERE id = :d"),
            {"d": bright["id"]},
        )
    assert not api.get("/referrals").json()[0]["converted"]

    for side in (client_id, bright["account_id"]):
        assert [r["id"] for r in api.get("/referrals", params={"account_id": side}).json()] == [
            referral["id"]
        ]
    events = [e["summary"] for e in api.get(f"/accounts/{client_id}/timeline").json()]
    assert "Referred Bright Dental to Verkies (Grace Okafor)." in events

    updated = api.send("PATCH", f"/referrals/{referral['id']}", json={"status": "contacted"})
    assert updated.json()["status"] == "contacted"
    board = api.get("/reports/management").json()
    table = next(t for t in board["tables"] if t["key"] == "referral_sources")
    assert table["rows"][0]["label"] == "Grace Okafor, Acme Legal"
    assert table["rows"][0]["values"][:2] == [1, 0]


def test_referral_rules_and_access(
    engine: Engine, api: ApiClient, admin: uuid.UUID, make_api: Callable[[], ApiClient]
) -> None:
    nobody = api.send("POST", "/referrals", json={"referred_company": "Bright Dental"})
    assert nobody.status_code == 422 and nobody.json()["error"]["code"] == "referrer_required"
    future = api.send(
        "POST",
        "/referrals",
        json={
            "referrer_name": "Tom at the chamber of commerce",
            "referred_company": "Bright Dental",
            "received_on": (datetime.now(UTC).date() + timedelta(days=1)).isoformat(),
        },
    )
    assert future.status_code == 422
    bad_domain = api.send(
        "POST",
        "/referrals",
        json={"referrer_name": "Tom", "referred_company": "X", "referred_domain": "not a site"},
    )
    assert bad_domain.status_code == 422

    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin)
    api.send(
        "POST", "/referrals", json={"referrer_account_id": str(acme), "referred_company": "Hidden"}
    )
    api.send(
        "POST",
        "/referrals",
        json={"referrer_name": "Tom at the chamber of commerce", "referred_company": "Open Co"},
    )
    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    assert [r["referred_company"] for r in seller.get("/referrals").json()] == ["Open Co"]
    hidden = api.get("/referrals").json()
    hidden_id = next(r["id"] for r in hidden if r["referred_company"] == "Hidden")
    assert (
        seller.send("PATCH", f"/referrals/{hidden_id}", json={"status": "declined"}).status_code
        == 404
    )
