"""Slice 5.3: learned proposals are made from outcomes and only a person activates them."""

import json
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_win_loss import close

pytestmark = pytest.mark.integration


@pytest.fixture
def admin(engine: Engine, api: ApiClient) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    return user_id


def history(engine: Engine, api: ApiClient, owner: uuid.UUID) -> None:
    """Five legal wins scored high on ICP fit, five retail losses scored low."""
    for i in range(5):
        won = close(engine, api, owner, f"Legal {i}", won=True, industry="legal")
        lost = close(engine, api, owner, f"Shop {i}", won=False, industry="retail")
        with engine.begin() as conn:
            for deal, icp in ((won, 85 + i), (lost, 30 + i)):
                conn.execute(
                    text(
                        "UPDATE deal_outcomes SET first_scores = CAST(:s AS jsonb)"
                        " WHERE deal_id = :d"
                    ),
                    {
                        "s": json.dumps({"icp_score": icp, "priority_score": icp}),
                        "d": deal["deal_id"],
                    },
                )


def test_too_few_outcomes(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    close(engine, api, admin, "Legal One", won=True, industry="legal")
    refused = api.send("POST", "/learning/proposals", json={"kind": "scoring"})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "not_enough_outcomes"
    assert refused.json()["error"]["details"] == {"won": 1, "lost": 0, "needed": 5}


def test_scoring_proposal_is_activated_only_by_a_person(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    history(engine, api, admin)
    before = api.get("/config/scoring").json()

    made = api.send("POST", "/learning/proposals", json={"kind": "scoring"})
    assert made.status_code == 201, made.text
    proposal = made.json()
    assert proposal["status"] == "proposed" and proposal["based_on_version"] == before["version"]
    assert proposal["basis"]["won"] == 5 and proposal["basis"]["lost"] == 5
    icp = next(c for c in proposal["changes"] if c["key"] == "icp_score")
    assert icp["from"] == 0.2 and icp["to"] > 0.2 and "Won deals first scored 87.0" in icp["why"]
    assert sum(proposal["proposed_config"]["weights"].values()) == pytest.approx(1)
    assert api.get("/config/scoring").json()["version"] == before["version"]  # nothing changed

    activated = api.send(
        "POST", f"/learning/proposals/{proposal['id']}/activate", json={"note": "Q3 review"}
    ).json()
    assert activated["status"] == "activated" and activated["decided_by"] == "Ada Admin"
    after = api.get("/config/scoring").json()
    assert after["version"] == before["version"] + 1 == activated["activated_version"]
    assert after["config"]["weights"] == proposal["proposed_config"]["weights"]
    assert after["note"] == "Q3 review"
    again = api.send("POST", f"/learning/proposals/{proposal['id']}/activate", json={})
    assert again.status_code == 409

    with engine.connect() as conn:
        actions = set(conn.execute(text("SELECT action FROM audit_log")).scalars())
    assert {
        "proposal.scoring.created",
        "proposal.scoring.activated",
        "config.scoring.updated",
    } <= actions


def test_stale_superseded_and_dismissed(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    history(engine, api, admin)
    first = api.send("POST", "/learning/proposals", json={"kind": "scoring"}).json()
    second = api.send("POST", "/learning/proposals", json={"kind": "scoring"}).json()
    assert second["proposed_config"] == first["proposed_config"]  # same data, same proposal
    assert second["basis"]["digest"] == first["basis"]["digest"]
    statuses = {p["id"]: p["status"] for p in api.get("/learning/proposals").json()}
    assert statuses == {first["id"]: "superseded", second["id"]: "proposed"}

    # Someone edits the config by hand: the proposal no longer applies to what is active.
    current = api.get("/config/scoring").json()["config"]
    api.send("PUT", "/config/scoring", json={"config": current, "note": "manual"})
    stale = api.send("POST", f"/learning/proposals/{second['id']}/activate", json={})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale"

    dismissed = api.send(
        "POST", f"/learning/proposals/{second['id']}/dismiss", json={"reason": "Too early to tell"}
    ).json()
    assert dismissed["status"] == "dismissed" and dismissed["decision_note"] == "Too early to tell"


def test_icp_proposal_moves_industry_tiers(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    history(engine, api, admin)
    proposal = api.send("POST", "/learning/proposals", json={"kind": "icp"}).json()
    moved = {c["key"]: (c["from"], c["to"]) for c in proposal["changes"]}
    assert moved == {"legal": ("A", "S"), "retail": ("B", "other")}
    api.send("POST", f"/learning/proposals/{proposal['id']}/activate", json={})
    tiers = api.get("/config/icp").json()["config"]["industry_tiers"]
    assert "legal" in tiers["S"] and "retail" not in tiers["B"]


def test_who_may_propose_and_activate(
    engine: Engine, api: ApiClient, admin: uuid.UUID, make_api: Callable[[], ApiClient]
) -> None:
    history(engine, api, admin)
    proposal = api.send("POST", "/learning/proposals", json={"kind": "scoring"}).json()

    make_user(engine, "max@verkies.test", ["sales_manager"], name="Max Manager")
    manager = make_api()
    manager.login("max@verkies.test")
    assert [p["id"] for p in manager.get("/learning/proposals").json()] == [proposal["id"]]
    assert manager.send("POST", "/learning/proposals", json={"kind": "scoring"}).status_code == 403
    blocked = manager.send("POST", f"/learning/proposals/{proposal['id']}/activate", json={})
    assert blocked.status_code == 403

    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    assert seller.get("/learning/proposals").status_code == 403
