"""Slice 2.6: top leads, plain-English search, duplicate review and account merge."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text

from tests.integration.conftest import ApiClient, make_user

pytestmark = pytest.mark.integration

BREAKDOWN = {
    "dimensions": {
        "icp_score": {
            "score": 90,
            "weight": 0.2,
            "contribution": 18.0,
            "evidence_ids": [],
            "note": "",
        },
        "opportunity_score": {
            "score": 80,
            "weight": 0.15,
            "contribution": 12.0,
            "evidence_ids": [],
            "note": "",
        },
        "timing_score": {
            "score": 60,
            "weight": 0.1,
            "contribution": 6.0,
            "evidence_ids": [],
            "note": "",
        },
        "client_similarity": {
            "score": None,
            "weight": 0.05,
            "contribution": None,
            "evidence_ids": [],
            "note": "",
        },
    },
    "unknown": ["client_similarity"],
    "gates": [{"gate": "coverage", "cap": 59, "applied": False, "why": "n/a"}],
}


def account(
    engine: Engine,
    name: str,
    *,
    domain: str | None = None,
    score: float | None = None,
    band: str | None = None,
    kind: str = "qualified_prospect",
    city: str | None = None,
    country: str | None = None,
    industry: str | None = None,
    description: str | None = None,
    legal_name: str | None = None,
    owner: uuid.UUID | None = None,
) -> uuid.UUID:
    account_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, name, legal_name, primary_domain, account_type,"
                " priority_score, priority_band, hq_city, hq_country, industry, description,"
                " owner_id)"
                " VALUES (:id, :n, :l, :d, :k, :s, :b, :c, :co, :i, :desc, :o)"
            ),
            {
                "id": account_id,
                "n": name,
                "l": legal_name,
                "d": domain,
                "k": kind,
                "s": score,
                "b": band,
                "c": city,
                "co": country,
                "i": industry,
                "desc": description,
                "o": owner,
            },
        )
        if domain:
            conn.execute(
                text(
                    "INSERT INTO account_domains (id, account_id, domain, is_primary)"
                    " VALUES (:id, :a, :d, true)"
                ),
                {"id": uuid.uuid4(), "a": account_id, "d": domain},
            )
    return account_id


def snapshot(engine: Engine, account_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO score_snapshots (id, account_id, scoring_config_id, priority_score,"
                " qualifies, breakdown) SELECT :id, :a, id, 82, true, CAST(:b AS jsonb)"
                " FROM scoring_configs WHERE is_active"
            ),
            {"id": uuid.uuid4(), "a": account_id, "b": json.dumps(BREAKDOWN)},
        )


def opportunity(engine: Engine, account_id: uuid.UUID, category: str) -> uuid.UUID:
    opp_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO opportunities (id, account_id, name, problem, category_id, stage)"
                " SELECT :id, :a, :n, 'Found on their site', id, 'qualified_opportunity'"
                " FROM opportunity_categories WHERE key = :k"
            ),
            {"id": opp_id, "a": account_id, "n": f"{category} for them", "k": category},
        )
    return opp_id


def signal(
    engine: Engine, account_id: uuid.UUID, user_id: uuid.UUID, kind: str, days_ago: int
) -> None:
    run_id, evidence_id = uuid.uuid4(), uuid.uuid4()
    published = datetime.now(UTC) - timedelta(days=days_ago)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO research_runs (id, input_url, normalised_domain, requested_by_id,"
                " status,"
                " review_status, retry_count, crawl_budget, possible_duplicate_of, account_id)"
                " VALUES (:id, 'https://x.test/', 'x.test', :u, 'completed', 'approved', 0, '{}',"
                " '[]', :a)"
            ),
            {"id": run_id, "u": user_id, "a": account_id},
        )
        conn.execute(
            text(
                "INSERT INTO evidence (id, research_run_id, source_url, source_domain,"
                " collected_at,"
                " published_at, evidence_type, evidence_text, content_hash, confidence)"
                " VALUES (:id, :r, 'https://jobs.test/1', 'jobs.test', now(), :p, 'job_posting',"
                " 'Senior Python Developer', 'h', 0.9)"
            ),
            {"id": evidence_id, "r": run_id, "p": published},
        )
        conn.execute(
            text(
                "INSERT INTO observations (id, research_run_id, attempt, area, key, value,"
                " evidence_id,"
                " seen_on, confidence) VALUES (:id, :r, 0, 'signals', 'signal.job_posting',"
                " CAST(:v AS jsonb), :e, '[]', 0.9)"
            ),
            {
                "id": uuid.uuid4(),
                "r": run_id,
                "v": json.dumps({"signal": kind, "title": "Senior Python Developer"}),
                "e": evidence_id,
            },
        )


@pytest.fixture
def admin(engine: Engine, api: ApiClient) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    return user_id


def test_top_leads_rank_open_prospects_and_explain_each_rank(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    best = account(engine, "Harbour Immigration", domain="harbour.test", score=82, band="high")
    account(engine, "Old Mill Bakery", domain="oldmill.test", score=61, band="qualified")
    account(engine, "Rejected Ltd", domain="rejected.test", score=30, band="reject")
    account(engine, "Unscored Ltd", domain="unscored.test")
    account(engine, "Happy Client", domain="client.test", score=95, band="hot", kind="customer")
    suppressed = account(engine, "Do Not Contact", domain="dnc.test", score=90, band="hot")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO suppressions (id, kind, value, reason)"
                " VALUES (gen_random_uuid(), 'domain', 'dnc.test', 'asked')"
            )
        )
    snapshot(engine, best)
    signal(engine, best, admin, "developer_hiring", days_ago=10)
    opportunity(engine, best, "client_portal")

    response = api.get("/leads/top", params={"limit": 20})
    assert response.status_code == 200, response.text
    leads = response.json()
    assert [lead["account"]["name"] for lead in leads] == ["Harbour Immigration", "Old Mill Bakery"]
    assert str(suppressed) not in {lead["account"]["id"] for lead in leads}

    reasons = {(r["kind"], r["text"]) for r in leads[0]["reasons"]}
    assert ("score", "ICP fit 90 (20% of the priority score)") in reasons
    assert ("unknown", "Unknown, not counted: Client similarity") in reasons
    hiring = next(r for r in leads[0]["reasons"] if r["kind"] == "signal")
    assert hiring["text"].startswith("Hiring developers: Senior Python Developer (")
    assert hiring["source_url"] == "https://jobs.test/1"
    assert any(r["kind"] == "opportunity" for r in leads[0]["reasons"])
    assert leads[1]["reasons"] == [
        {"kind": "unknown", "text": "Not scored yet", "source_url": None}
    ]


def test_search_reads_plain_english_into_filters(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    london = account(
        engine,
        "Harbour Immigration",
        score=80,
        band="high",
        city="London",
        country="GB",
        industry="Legal",
    )
    leeds = account(
        engine, "Leeds Legal", score=85, band="high", city="Leeds", country="GB", industry="Legal"
    )
    account(
        engine,
        "London Bakery",
        score=70,
        band="qualified",
        city="London",
        country="GB",
        industry="Food",
    )
    opportunity(engine, london, "crm")
    opportunity(engine, leeds, "seo")
    signal(engine, london, admin, "developer_hiring", days_ago=20)
    signal(engine, leeds, admin, "developer_hiring", days_ago=400)

    found = api.get(
        "/leads/search",
        params={"q": "London legal firms that could benefit from CRM and client portals"},
    ).json()
    assert [r["account"]["name"] for r in found["results"]] == ["Harbour Immigration"]
    meanings = {u["phrase"]: u["meaning"] for u in found["interpretation"]["understood"]}
    assert meanings["london"] == "Located in London"
    assert meanings["legal"] == "Industry is legal"
    assert meanings["crm"].startswith("Opportunity detected")

    hiring = api.get(
        "/leads/search", params={"q": "UK companies hiring developers within the last 6 months"}
    ).json()
    assert [r["account"]["name"] for r in hiring["results"]] == [
        "Harbour Immigration"
    ]  # Leeds' signal is too old

    top = api.get(
        "/leads/search", params={"q": "Find 2 companies Verkies should contact this week"}
    ).json()
    assert top["interpretation"]["top_leads"] is True
    assert top["interpretation"]["limit"] == 2
    assert [r["rank"] for r in top["results"]] == [1, 2]

    similar = api.get("/leads/search", params={"q": "businesses similar to Wesbridge"}).json()
    assert similar["interpretation"]["unsupported"][0]["phrase"] == "similar to wesbridge"


def test_duplicates_are_suggested_dismissed_and_merged(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    keep = account(engine, "Harbour Immigration Ltd", domain="harbour.test", score=80, band="high")
    gone = account(
        engine,
        "Harbour Immigration",
        domain="harbour.co.uk",
        legal_name="Harbour Immigration Limited",
        city="London",
        description="Immigration advisers.",
    )
    other = account(engine, "Harbour Bakery", domain="harbourbakery.test")
    opportunity(engine, gone, "crm")
    signal(engine, gone, admin, "funding", days_ago=5)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO contacts (id, account_id, name, source, collected_at, confidence,"
                " verification_status, lawful_basis) VALUES (gen_random_uuid(), :a, 'Amelia Hart',"
                " 'website', now(), 0.8, 'unverified', 'b2b_legitimate_interest')"
            ),
            {"a": gone},
        )
        conn.execute(
            text(
                "INSERT INTO timeline_events (id, account_id, event_type, summary)"
                " VALUES (gen_random_uuid(), :a, 'note', 'History on the duplicate')"
            ),
            {"a": gone},
        )

    pairs = api.get("/account-duplicates").json()
    names = [{p["account_a"]["name"], p["account_b"]["name"]} for p in pairs]
    assert {"Harbour Immigration Ltd", "Harbour Immigration"} in names
    pair = next(
        p for p in pairs if {p["account_a"]["id"], p["account_b"]["id"]} == {str(keep), str(gone)}
    )
    assert any(r.startswith("Similar names") for r in pair["reasons"])
    assert "Same website name: harbour.test and harbour.co.uk" in pair["reasons"] or (
        "Same website name: harbour.co.uk and harbour.test" in pair["reasons"]
    )

    if any({p["account_a"]["id"], p["account_b"]["id"]} == {str(keep), str(other)} for p in pairs):
        dismissed = api.send(
            "POST",
            "/account-duplicates/dismiss",
            json={"account_a_id": str(other), "account_b_id": str(keep)},
        )
        assert dismissed.status_code == 204, dismissed.text
        again = api.get("/account-duplicates").json()
        assert not any(
            {p["account_a"]["id"], p["account_b"]["id"]} == {str(keep), str(other)} for p in again
        )

    assert (
        api.send(
            "POST", f"/accounts/{keep}/merge", json={"merge_id": str(gone), "reason": "x"}
        ).status_code
        == 422
    )
    merged = api.send(
        "POST",
        f"/accounts/{keep}/merge",
        json={"merge_id": str(gone), "reason": "Same company, two websites"},
    )
    assert merged.status_code == 200, merged.text
    body = merged.json()
    assert body["moved"]["contacts"] == 1
    assert body["moved"]["opportunities"] == 1
    assert body["moved"]["account_domains"] == 1
    assert set(body["filled"]) >= {"legal_name", "hq_city", "description"}

    survivor = api.get(f"/accounts/{keep}").json()
    assert survivor["legal_name"] == "Harbour Immigration Limited"
    assert set(survivor["domains"]) == {"harbour.test", "harbour.co.uk"}
    assert [c["name"] for c in survivor["contacts"]] == ["Amelia Hart"]

    old_link = api.get(f"/accounts/{gone}")
    assert old_link.status_code == 404
    assert old_link.json()["error"] == {
        "code": "merged",
        "message": "This account was merged into another.",
        "details": {"merged_into": str(keep)},
    }

    timeline = [e["summary"] for e in api.get(f"/accounts/{keep}/timeline").json()]
    assert "History on the duplicate" in timeline  # append-only history read with the survivor
    assert any(
        s.startswith("Harbour Immigration (harbour.co.uk) merged into this account")
        for s in timeline
    )
    audit = api.get(f"/accounts/{keep}/audit").json()
    entry = next(e for e in audit if e["action"] == "account.merged")
    assert entry["reason"] == "Same company, two websites"

    # Signals on the retired account's research now count for the survivor.
    found = api.get("/leads/search", params={"q": "companies that raised funding"}).json()
    assert [r["account"]["id"] for r in found["results"]] == [str(keep)]
    assert all(
        str(gone) not in {p["account_a"]["id"], p["account_b"]["id"]}
        for p in api.get("/account-duplicates").json()
    )
    assert (
        api.send(
            "POST", f"/accounts/{keep}/merge", json={"merge_id": str(gone), "reason": "again"}
        ).status_code
        == 404
    )


def test_merging_needs_the_merge_permission(engine: Engine, api: ApiClient) -> None:
    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    api.login("sam@verkies.test")
    first = account(engine, "Acme", domain="acme.test")
    second = account(engine, "Acme Ltd", domain="acme.co.uk")
    assert api.get("/account-duplicates").status_code == 403
    response = api.send(
        "POST", f"/accounts/{first}/merge", json={"merge_id": str(second), "reason": "same"}
    )
    assert response.status_code == 403
    assert api.get("/leads/top").status_code == 200  # top leads are open to every member
