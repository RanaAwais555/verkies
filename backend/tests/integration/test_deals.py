"""Slice 3.1: pipelines, deals, stage moves, the forecast and who may see what."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text

from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_leads import account, opportunity

pytestmark = pytest.mark.integration

THIS_YEAR = datetime.now(UTC).year


@pytest.fixture
def admin(engine: Engine, api: ApiClient) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    return user_id


def stages(api: ApiClient, pipeline_key: str) -> dict[str, str]:
    pipelines = api.get("/pipelines").json()["pipelines"]
    pipeline = next(p for p in pipelines if p["key"] == pipeline_key)
    return {s["key"]: s["id"] for s in pipeline["stages"]}


def pipeline_id(api: ApiClient, key: str) -> str:
    return next(p["id"] for p in api.get("/pipelines").json()["pipelines"] if p["key"] == key)


def test_the_three_default_pipelines_are_seeded(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    body = api.get("/pipelines").json()
    pipelines = {p["key"]: p for p in body["pipelines"]}
    assert list(pipelines) == ["new_business", "expansion", "partnership"]
    new_business = [s["name"] for s in pipelines["new_business"]["stages"]]
    assert new_business[:3] == ["New", "Qualified", "Researching"]
    assert new_business[-3:] == ["Won", "Lost", "Nurture"]
    assert all(s["probability"] is None for s in pipelines["partnership"]["stages"])
    assert {r["key"] for r in body["lost_reasons"]} >= {
        "price",
        "no_budget",
        "another_agency",
        "other",
    }


def test_open_flag_and_clear_a_deal(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin)
    opp = opportunity(engine, acme, "crm")

    created = api.send("POST", "/deals", json={"opportunity_id": str(opp)})
    assert created.status_code == 201, created.text
    deal = created.json()
    assert deal["pipeline_key"] == "new_business"
    assert deal["stage_key"] == "qualified_opportunity"  # where an approved opportunity already is
    assert deal["value"] is None and deal["weighted_value"] is None  # never estimated
    assert deal["probability"] == 40 and deal["probability_is_stage_default"]
    assert deal["owner"]["id"] == str(admin)
    assert deal["requires_attention"] == ["no next task", "no expected close date"]

    again = api.send("POST", "/deals", json={"opportunity_id": str(opp)})
    assert again.status_code == 409
    assert again.json()["error"]["details"]["deal_id"] == deal["id"]

    task = api.send(
        "POST",
        "/tasks",
        json={
            "account_id": str(acme),
            "deal_id": deal["id"],
            "title": "Send the proposal",
            "owner_id": str(admin),
        },
    )
    assert task.status_code == 201, task.text
    assert task.json()["deal_id"] == deal["id"]
    assert task.json()["opportunity_id"] == str(opp)  # also the opportunity's next action

    updated = api.send(
        "PATCH",
        f"/deals/{deal['id']}",
        json={"value": "12000.00", "expected_close": f"{THIS_YEAR + 1}-02-15"},
    ).json()
    assert updated["value"] == 12000 and updated["weighted_value"] == 4800
    assert updated["next_task"]["title"] == "Send the proposal"
    assert updated["requires_attention"] == []


def test_moving_losing_and_reopening_a_deal(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    acme = account(engine, "Acme Legal", domain="acme.test", owner=admin)
    opp = opportunity(engine, acme, "crm")
    deal = api.send("POST", "/deals", json={"opportunity_id": str(opp), "value": "5000"}).json()
    nb = stages(api, "new_business")
    partnership = stages(api, "partnership")

    wrong = api.send(
        "POST", f"/deals/{deal['id']}/move", json={"stage_id": partnership["conversation"]}
    )
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "wrong_pipeline"

    proposal = api.send(
        "POST", f"/deals/{deal['id']}/move", json={"stage_id": nb["proposal"]}
    ).json()
    assert proposal["stage_name"] == "Proposal" and proposal["weighted_value"] == 3000
    assert proposal["days_in_stage"] == 0

    no_reason = api.send("POST", f"/deals/{deal['id']}/move", json={"stage_id": nb["lost"]})
    assert (
        no_reason.status_code == 422 and no_reason.json()["error"]["code"] == "lost_reason_required"
    )

    lost = api.send(
        "POST",
        f"/deals/{deal['id']}/move",
        json={
            "stage_id": nb["lost"],
            "lost_reason": "another_agency",
            "lost_note": "Went with their usual agency",
        },
    ).json()
    assert lost["outcome"] == "lost" and lost["closed_at"] is not None
    assert lost["lost_reason"] == "another_agency" and lost["requires_attention"] == []
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT stage FROM opportunities WHERE id = :o"), {"o": opp}
            ).scalar_one()
            == "lost"
        )

    reopened = api.send(
        "POST", f"/deals/{deal['id']}/move", json={"stage_id": nb["negotiation"]}
    ).json()
    assert (
        reopened["outcome"] == "open"
        and reopened["closed_at"] is None
        and reopened["lost_reason"] is None
    )

    timeline = [e["summary"] for e in api.get(f"/accounts/{acme}/timeline").json()]
    assert any("moved from Proposal to Lost. Reason: Another agency." in s for s in timeline)
    assert any(
        s.startswith("Deal opened in New Business at Qualified Opportunity") for s in timeline
    )
    actions = [e["action"] for e in api.get(f"/accounts/{acme}/audit").json()]
    assert actions.count("deal.stage_changed") == 3
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM deal_stage_changes")).scalar_one() == 4


def test_forecast_counts_unknowns_instead_of_zeroing_them(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    nb = stages(api, "new_business")
    first = account(engine, "First", domain="first.test")
    second = account(engine, "Second", domain="second.test")
    partner = account(engine, "Partner Co", domain="partner.test", kind="partner")

    def deal(account_id: uuid.UUID, **body: object) -> str:
        response = api.send("POST", "/deals", json={"account_id": str(account_id), **body})
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    big = deal(first, value="10000", expected_close=f"{THIS_YEAR + 1}-03-10")
    api.send("POST", f"/deals/{big}/move", json={"stage_id": nb["proposal"]})  # 60%
    deal(second)  # value unknown
    partnership = deal(partner, value="5000")  # partnership stages carry no probability
    won = deal(first, value="2000")
    api.send("POST", f"/deals/{won}/move", json={"stage_id": nb["won"]})
    lost = deal(second, value="1000")
    api.send("POST", f"/deals/{lost}/move", json={"stage_id": nb["lost"], "lost_reason": "price"})
    unknown_win = deal(second)
    api.send("POST", f"/deals/{unknown_win}/move", json={"stage_id": nb["won"]})

    assert api.get(f"/deals/{partnership}").json()["pipeline_key"] == "partnership"
    [gbp] = api.get("/deals/forecast").json()
    assert gbp["open_count"] == 3
    assert gbp["open_value"] == 15000
    assert gbp["unknown_value_count"] == 1
    assert gbp["weighted_value"] == 6000
    assert gbp["unweighted_count"] == 1
    assert gbp["no_close_date_count"] == 1
    assert gbp["months"] == [
        {"month": f"{THIS_YEAR + 1}-03", "count": 1, "value": 10000, "weighted": 6000}
    ]
    assert (gbp["won_count"], gbp["won_value"], gbp["won_unknown_value_count"]) == (2, 2000, 1)
    assert (gbp["lost_count"], gbp["lost_value"]) == (1, 1000)

    only_nb = api.get(
        "/deals/forecast", params={"pipeline_id": pipeline_id(api, "new_business")}
    ).json()
    assert only_nb[0]["open_count"] == 2


def test_salespeople_see_deals_only_on_accounts_they_may_see(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    sam = make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    mine = account(engine, "Mine", domain="mine.test", owner=sam)
    theirs = account(engine, "Theirs", domain="theirs.test", owner=admin)
    hidden = api.send("POST", "/deals", json={"account_id": str(theirs)}).json()
    api.login("sam@verkies.test")

    assert api.send("POST", "/deals", json={"account_id": str(mine)}).status_code == 201
    assert api.send("POST", "/deals", json={"account_id": str(theirs)}).status_code == 404
    assert api.get(f"/deals/{hidden['id']}").status_code == 404
    assert [d["account_name"] for d in api.get("/deals").json()] == ["Mine"]
    assert (
        api.send(
            "PATCH", f"/pipeline-stages/{hidden['stage_id']}", json={"probability": 50}
        ).status_code
        == 403
    )


def test_a_merge_takes_the_deals_with_it(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    keep = account(engine, "Harbour Immigration Ltd", domain="harbour.test")
    gone = account(engine, "Harbour Immigration", domain="harbour.co.uk")
    deal = api.send("POST", "/deals", json={"account_id": str(gone), "value": "3000"}).json()
    merged = api.send(
        "POST", f"/accounts/{keep}/merge", json={"merge_id": str(gone), "reason": "Same company"}
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["moved"]["deals"] == 1
    assert api.get(f"/deals/{deal['id']}").json()["account_id"] == str(keep)
