"""Slice 3.3: dashboards, the conversion funnel and saved views, each figure checked by hand."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text

from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_activities import log
from tests.integration.test_deals import admin, stages  # noqa: F401 - fixture
from tests.integration.test_leads import account, opportunity, signal

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


def run(
    engine: Engine,
    domain: str,
    user: uuid.UUID,
    *,
    account_id: uuid.UUID | None = None,
    review: str = "pending",
    reason: str | None = None,
    days_ago: int = 1,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO research_runs (id, input_url, normalised_domain, requested_by_id,"
                " status, review_status, retry_count, crawl_budget, possible_duplicate_of,"
                " account_id, created_at, reviewed_at, rejection_reason)"
                " VALUES (gen_random_uuid(), :url, :d, :u, 'completed', :r, 0, '{}', '[]', :a,"
                " :t, :reviewed, :reason)"
            ),
            {
                "url": f"https://{domain}/",
                "d": domain,
                "u": user,
                "r": review,
                "a": account_id,
                "t": NOW - timedelta(days=days_ago),
                "reviewed": None if review == "pending" else NOW - timedelta(days=days_ago),
                "reason": reason,
            },
        )


def lead(
    engine: Engine,
    account_id: uuid.UUID,
    *,
    score: float | None,
    band: str | None,
    source: str = "research",
    days_ago: int = 1,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO leads (id, account_id, source, status, priority_score, priority_band,"
                " qualified_at, created_at) VALUES (gen_random_uuid(), :a, :s, 'qualified', :sc,"
                " :b, :t, :t)"
            ),
            {
                "a": account_id,
                "s": source,
                "sc": score,
                "b": band,
                "t": NOW - timedelta(days=days_ago),
            },
        )


def figures(body: dict) -> dict[str, dict]:  # type: ignore[type-arg]
    return {f["key"]: f for f in body["figures"]}


def table(body: dict, key: str) -> dict[str, list]:  # type: ignore[type-arg]
    found = next(t for t in body["tables"] if t["key"] == key)
    return {r["label"]: r["values"] for r in found["rows"]}


def test_an_empty_sales_dashboard_says_unknown_not_zero(
    engine: Engine,
    api: ApiClient,
    admin: uuid.UUID,  # noqa: F811
) -> None:
    body = api.get("/reports/sales").json()
    f = figures(body)
    assert body["period"] == "90d"
    assert f["new_leads"]["value"] == 0 and f["deals_opened"]["value"] == 0
    assert f["win_rate"]["value"] is None  # nothing closed: unknown, not 0%
    assert f["sales_cycle"]["value"] is None
    assert f["won_value"]["value"] == 0 and f["won_value"]["detail"] == "0 deals"
    assert all(fig["definition"] for fig in body["figures"])
    assert [s["count"] for s in body["funnel"]] == [0] * 8
    assert api.get("/reports/sales?period=bad").status_code == 422


def test_sales_figures_from_real_deals(
    engine: Engine,
    api: ApiClient,
    admin: uuid.UUID,  # noqa: F811
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin)
    nb = stages(api, "new_business")
    deal_ids = []
    for category, value in (
        ("crm", "5000"),
        ("seo", None),
        ("client_portal", "10000"),
        ("website_rebuild", None),
    ):
        opp = opportunity(engine, acme, category)
        body = {"opportunity_id": str(opp), **({"value": value} if value else {})}
        deal_ids.append(api.send("POST", "/deals", json=body).json()["id"])
    won, lost, proposal, unknown = deal_ids
    api.send("POST", f"/deals/{won}/move", json={"stage_id": nb["won"]})
    api.send(
        "POST",
        f"/deals/{lost}/move",
        json={"stage_id": nb["lost"], "lost_reason": "price"},
    )
    api.send("POST", f"/deals/{proposal}/move", json={"stage_id": nb["proposal"]})
    with engine.begin() as conn:  # the won deal was opened ten days before it was won
        conn.execute(
            text("UPDATE deals SET created_at = closed_at - interval '10 days' WHERE id = :d"),
            {"d": won},
        )
    log(api, acme, kind="call", call_outcome="connected", summary="Spoke.")
    log(api, acme, kind="note", summary="Prefers email.")

    body = api.get("/reports/sales").json()
    f = figures(body)
    assert f["pipeline"]["value"] == 10000
    assert f["pipeline"]["detail"] == "2 deals; 1 without a value, not counted"
    assert f["weighted_pipeline"]["value"] == 6000  # 10,000 at Proposal's 60%
    assert f["won_value"]["value"] == 5000
    assert f["lost_value"]["value"] is None  # the lost deal never had a value
    assert f["win_rate"]["value"] == 50 and f["win_rate"]["detail"] == "1 of 2 closed deals"
    assert f["sales_cycle"]["value"] == 10
    assert f["deals_opened"]["value"] == 4
    activity = table(body, "activity")
    assert activity["Calls"] == [1] and activity["Notes"] == [1] and activity["Meetings"] == [0]
    # The won and lost deals' opportunities are closed; the two open ones lack a next action.
    assert table(body, "follow_ups")["No next action"] == [2]
    assert unknown in deal_ids

    sam = make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    mine = figures(api.get("/reports/sales?mine=true").json())
    assert mine["deals_opened"]["value"] == 4  # Ada owns the deals, so they are hers
    assert sam not in (None, admin)


def test_the_funnel_counts_each_company_at_its_furthest_step(
    engine: Engine,
    api: ApiClient,
    admin: uuid.UUID,  # noqa: F811
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin)
    globex = account(engine, "Globex", domain="globex.test", owner=admin)
    run(engine, "acme.test", admin, account_id=acme, review="approved")
    run(engine, "globex.test", admin, account_id=globex, review="approved")
    run(engine, "initech.test", admin, review="rejected", reason="wrong_icp")
    run(engine, "old.test", admin, days_ago=200)  # outside the period
    lead(engine, acme, score=80, band="hot")
    lead(engine, globex, score=55, band="qualified")

    # Acme goes all the way; Globex only gets an unanswered call.
    log(api, acme, kind="message", message_channel="email", summary="Intro sent.")
    log(api, acme, kind="message", message_channel="email", received=True, summary="Interested.")
    log(api, acme, kind="meeting", summary="Discovery.")
    deal = api.send(
        "POST", "/deals", json={"opportunity_id": str(opportunity(engine, acme, "crm"))}
    )
    nb = stages(api, "new_business")
    for key in ("proposal", "won"):
        api.send("POST", f"/deals/{deal.json()['id']}/move", json={"stage_id": nb[key]})
    log(api, globex, kind="call", call_outcome="no_answer", summary="Rang.")

    steps = {s["key"]: s["count"] for s in api.get("/reports/sales").json()["funnel"]}
    assert steps == {
        "discovered": 3,
        "qualified": 2,
        "contacted": 2,
        "reply": 1,
        "meeting": 1,
        "opportunity": 1,
        "proposal": 1,
        "won": 1,
    }
    assert steps["discovered"] == 3  # a rejected prospect was still discovered
    year = {s["key"]: s["count"] for s in api.get("/reports/sales?period=365d").json()["funnel"]}
    assert year["discovered"] == 4


def test_lead_intelligence(
    engine: Engine,
    api: ApiClient,
    admin: uuid.UUID,  # noqa: F811
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin, industry="Legal")
    globex = account(engine, "Globex", domain="globex.test", owner=admin)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE accounts SET hq_country = 'GB', data_confidence = 70, icp_score = 82"
                " WHERE id = :a"
            ),
            {"a": acme},
        )
    run(engine, "acme.test", admin, account_id=acme, review="approved")
    run(engine, "globex.test", admin, account_id=globex, review="approved")
    run(engine, "rival.test", admin, review="rejected", reason="competitor")
    run(engine, "tiny.test", admin, review="rejected", reason="unsuitable_company_size")
    lead(engine, acme, score=84, band="hot")
    lead(engine, globex, score=None, band=None)
    signal(engine, acme, admin, "developer_hiring", days_ago=5)
    signal(engine, acme, admin, "funding", days_ago=400)  # too old for the period

    body = api.get("/reports/lead-intelligence").json()
    f = figures(body)
    assert f["qualification_rate"]["value"] == 50 and f["rejection_rate"]["value"] == 50
    assert f["lead_quality"]["value"] == 84
    assert f["lead_quality"]["detail"] == "1 scored of 2 qualified"
    assert f["data_confidence"]["value"] == 70
    assert table(body, "rejection_reasons") == {"Competitor": [1], "Unsuitable company size": [1]}
    assert table(body, "priority_bands") == {"Hot": [1], "Unscored": [1]}
    assert table(body, "industries") == {"Legal": [1], "Industry unknown": [1]}
    assert table(body, "geographies") == {"United Kingdom": [1], "Country unknown": [1]}
    assert table(body, "signals") == {"Hiring developers": [1]}
    icp = table(body, "icp_performance")
    assert icp["Unknown ICP"] == [1, 0, 0] and next(iter(icp.values())) == [1, 0, 0]
    distribution = table(body, "score_distribution")
    assert sum(v[0] for v in distribution.values()) == 1 and len(distribution) == 10


def test_management_is_for_managers_and_explains_losses(
    engine: Engine,
    api: ApiClient,
    make_api,  # type: ignore[no-untyped-def]
    admin: uuid.UUID,  # noqa: F811
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin, industry="Legal")
    nb = stages(api, "new_business")
    closing = (NOW + timedelta(days=10)).date().isoformat()
    soon = api.send(
        "POST",
        "/deals",
        json={
            "opportunity_id": str(opportunity(engine, acme, "crm")),
            "value": "8000",
            "expected_close": closing,
        },
    ).json()
    lost = api.send(
        "POST",
        "/deals",
        json={"opportunity_id": str(opportunity(engine, acme, "seo")), "value": "3000"},
    ).json()
    api.send(
        "POST",
        f"/deals/{lost['id']}/move",
        json={"stage_id": nb["lost"], "lost_reason": "another_agency"},
    )
    body = api.get("/reports/management").json()
    f = figures(body)
    assert f["win_rate"]["value"] == 0  # one closed deal, lost: a real 0%
    assert f["average_deal"]["value"] is None
    assert table(body, "likely_closes") == {
        f"Acme Legal · {soon['name']}": [
            closing,
            [{"amount": 8000.0, "currency": "GBP"}],
            40.0,
            "Ada Admin",
        ]
    }
    assert table(body, "lost_reasons") == {
        "Another agency": [1, [{"amount": 3000.0, "currency": "GBP"}]]
    }
    assert table(body, "industries_that_convert") == {"Legal": [0, 1, 0.0]}
    people = table(body, "salespeople")["Ada Admin"]
    assert people[0] == 1 and people[4] == 1  # one open deal, one lost

    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    assert seller.get("/reports/management").status_code == 403
    assert seller.get("/reports/lead-intelligence").status_code == 200  # reviews prospects
    assert seller.get("/reports/sales").status_code == 200


def test_saved_views(
    engine: Engine,
    api: ApiClient,
    make_api,  # type: ignore[no-untyped-def]
    admin: uuid.UUID,  # noqa: F811
) -> None:
    team = api.get("/saved-views").json()
    assert [v["name"] for v in team] == [
        "My Hot Leads",
        "Follow-ups Today",
        "Stale Opportunities",
        "UK SaaS Prospects",
        "High Value Pipeline",
        "New Buying Signals",
        "Unassigned Leads",
        "Deals Closing This Month",
    ]
    assert team[0] == {**team[0], "path": "/leads", "query": "q=my+hot+leads", "shared": True}
    assert all(v["can_delete"] for v in team)  # an admin manages the team's views

    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    mine = seller.send(
        "POST",
        "/saved-views",
        json={"name": "Leeds legal", "path": "/leads", "query": "?q=legal+in+leeds"},
    )
    assert mine.status_code == 201, mine.text
    assert mine.json()["query"] == "q=legal+in+leeds" and not mine.json()["shared"]
    views = seller.get("/saved-views").json()
    assert views[-1]["name"] == "Leeds legal" and not any(v["can_delete"] for v in views[:-1])
    assert all(v["name"] != "Leeds legal" for v in api.get("/saved-views").json())  # private

    assert (
        seller.send(
            "POST", "/saved-views", json={"name": "x", "path": "/leads", "shared": True}
        ).status_code
        == 403
    )
    assert (
        seller.send(
            "POST", "/saved-views", json={"name": "x", "path": "https://evil.test/"}
        ).status_code
        == 422
    )
    assert seller.send("DELETE", f"/saved-views/{team[0]['id']}").status_code == 403
    assert api.send("DELETE", f"/saved-views/{mine.json()['id']}").status_code == 404
    assert seller.send("DELETE", f"/saved-views/{mine.json()['id']}").status_code == 204

    shared = api.send(
        "POST",
        "/saved-views",
        json={"name": "Partners", "path": "/pipeline", "query": "tab=partnership", "shared": True},
    )
    assert shared.status_code == 201 and shared.json()["shared"]
    assert seller.get("/saved-views").json()[-1]["name"] == "Partners"
    assert api.send("DELETE", f"/saved-views/{team[1]['id']}").status_code == 204
    with engine.connect() as conn:
        actions = set(
            conn.execute(
                text("SELECT action FROM audit_log WHERE object_table = 'saved_views'")
            ).scalars()
        )
    assert actions == {"saved_view.shared", "saved_view.removed"}
