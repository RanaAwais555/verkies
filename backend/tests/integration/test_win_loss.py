"""Slice 5.2: win/loss analysis over recorded deal outcomes."""

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from app.config import get_settings
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_deals import stages
from tests.integration.test_leads import account, opportunity, signal

pytestmark = pytest.mark.integration


@pytest.fixture
def admin(engine: Engine, api: ApiClient) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    return user_id


def close(
    engine: Engine,
    api: ApiClient,
    owner: uuid.UUID,
    name: str,
    *,
    won: bool,
    industry: str,
    hiring: bool = False,
    value: str = "10000",
    feedback: str | None = None,
) -> dict:  # type: ignore[type-arg]
    acme = account(
        engine, name, domain=f"{name.lower().replace(' ', '')}.test", owner=owner, industry=industry
    )
    if hiring:
        signal(engine, acme, owner, "developer_hiring", days_ago=10)
    opp = opportunity(engine, acme, "crm")
    if feedback:  # given while the deal was open, so it counts
        api.send("POST", f"/accounts/{acme}/sales-feedback", json={"kind": feedback})
    deal = api.send("POST", "/deals", json={"opportunity_id": str(opp), "value": value}).json()
    nb = stages(api, "new_business")
    body = {"stage_id": nb["won"]} if won else {"stage_id": nb["lost"], "lost_reason": "price"}
    moved = api.send("POST", f"/deals/{deal['id']}/move", json=body)
    assert moved.status_code == 200, moved.text
    return {"account_id": str(acme), "deal_id": deal["id"]}


def test_win_loss_by_what_was_true_at_the_close(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    first = close(engine, api, admin, "Legal One", won=False, industry="legal", feedback="bad_lead")
    # Feedback after the close says nothing about how the lead looked beforehand.
    api.send("POST", f"/accounts/{first['account_id']}/sales-feedback", json={"kind": "lost"})
    close(engine, api, admin, "Legal Two", won=True, industry="legal", hiring=True)
    close(engine, api, admin, "Legal Three", won=True, industry="legal", hiring=True, value="20000")
    close(engine, api, admin, "Legal Four", won=True, industry="legal")
    close(engine, api, admin, "Legal Five", won=False, industry="legal")
    close(engine, api, admin, "Shop One", won=True, industry="retail")

    body = api.get("/learning/win-loss").json()
    assert body["min_sample"] == 5 and body["captured_late"] == 0
    overall = body["overall"]
    assert (overall["won"], overall["lost"], overall["total"]) == (4, 2, 6)
    assert overall["win_rate"] == pytest.approx(4 / 6)
    assert overall["won_value"] == [{"amount": 50000.0, "currency": "GBP"}]
    assert overall["avg_days_to_win"] == 0

    industry = {
        g["label"]: g
        for g in next(d for d in body["dimensions"] if d["key"] == "industry")["groups"]
    }
    assert (industry["Legal"]["won"], industry["Legal"]["lost"]) == (3, 2)
    assert industry["Legal"]["win_rate"] == pytest.approx(0.6)
    assert industry["Retail"]["total"] == 1 and industry["Retail"]["win_rate"] is None  # too few

    service = next(d for d in body["dimensions"] if d["key"] == "service")["groups"]
    assert [g["label"] for g in service] == ["Unknown"]  # never folded into another group
    opportunity_type = next(d for d in body["dimensions"] if d["key"] == "opportunity_type")
    assert [g["label"] for g in opportunity_type["groups"]] == ["CRM"]

    hiring = next(s for s in body["signals"] if s["signal"] == "developer_hiring")
    assert hiring["label"] == "Hiring developers"
    assert (hiring["with_signal"]["won"], hiring["with_signal"]["lost"]) == (2, 0)
    assert hiring["with_signal"]["win_rate"] is None  # 2 deals are too few to learn from
    assert hiring["without_signal"]["total"] == 4

    assert body["lost_reasons"] == [{"reason": "Price", "deals": 2}]
    assert [(g["label"], g["lost"]) for g in body["feedback"]] == [("Bad lead", 1)]


def test_period_pipeline_and_minimum_sample(
    engine: Engine, api: ApiClient, admin: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = close(engine, api, admin, "Old Win", won=True, industry="legal")
    close(engine, api, admin, "New Loss", won=False, industry="legal")
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE deal_outcomes SET closed_at = now() - interval '2 years' WHERE deal_id = :d"
            ),
            {"d": old["deal_id"]},
        )
    assert api.get("/learning/win-loss").json()["overall"]["total"] == 1
    assert api.get("/learning/win-loss", params={"months": 0}).json()["overall"]["total"] == 2
    assert (
        api.get("/learning/win-loss", params={"pipeline": "expansion"}).json()["overall"]["total"]
        == 0
    )

    monkeypatch.setenv("VROS_LEARNING_MIN_SAMPLE", "2")
    get_settings.cache_clear()
    everything = api.get("/learning/win-loss", params={"months": 0}).json()
    assert everything["min_sample"] == 2 and everything["overall"]["win_rate"] == 0.5


def test_people_learn_only_from_accounts_they_can_see(
    engine: Engine, api: ApiClient, admin: uuid.UUID, make_api: Callable[[], ApiClient]
) -> None:
    close(engine, api, admin, "Legal One", won=True, industry="legal")
    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    assert seller.get("/learning/win-loss").json()["overall"]["total"] == 0
    assert api.get("/learning/win-loss").json()["overall"]["total"] == 1
