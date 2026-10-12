"""Slice 4.2: client health, feedback, the retention engine and former clients."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text

from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_clients import won_deal

pytestmark = pytest.mark.integration

TODAY = datetime.now(UTC).date()


@pytest.fixture
def admin(engine: Engine, api: ApiClient) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    return user_id


def client(
    engine: Engine, api: ApiClient, owner: uuid.UUID, name: str = "Acme Legal"
) -> tuple[str, str]:
    """A client with one active project: (account_id, project_id)."""
    deal = won_deal(engine, api, owner, name)
    body = api.send(
        "POST",
        f"/deals/{deal['id']}/convert",
        json={
            "account_manager_id": str(owner),
            "project": {"name": "Portal", "status": "active"},
            "kickoff_task": False,
        },
    ).json()
    return body["account_id"], body["project_id"]


def risk_tasks(engine: Engine, account_id: str) -> list[tuple[str, str | None]]:
    with engine.connect() as conn:
        return [
            (t, str(o) if o else None)
            for t, o in conn.execute(
                text(
                    "SELECT title, owner_id FROM tasks WHERE account_id = :a"
                    " AND title LIKE 'Client risk detected%' AND status = 'open'"
                ),
                {"a": account_id},
            ).all()
        ]


def test_health_is_read_from_the_records(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    account_id, project_id = client(engine, api, admin)
    clients = api.get("/clients").json()
    assert [(c["name"], c["health"], c["reasons"]) for c in clients] == [
        ("Acme Legal", "green", [])
    ]
    assert clients[0]["account_manager"]["name"] == "Ada Admin"
    assert clients[0]["open_projects"] == 1 and clients[0]["client_since"] == TODAY.isoformat()

    api.send("PATCH", f"/projects/{project_id}", json={"status": "on_hold"})
    assert api.get("/clients").json()[0]["health"] == "yellow"
    api.send(
        "POST",
        f"/projects/{project_id}/risks",
        json={"description": "The CTO who signed has left", "severity": "high"},
    )
    current = api.get(f"/accounts/{account_id}/health").json()["current"]
    assert current["health"] == "red"
    assert [(r["level"], r["text"]) for r in current["reasons"]] == [
        ("red", "Portal: high risk open: The CTO who signed has left"),
        ("yellow", "Portal is on hold"),
    ]
    assert [c["name"] for c in api.get("/clients", params={"health": "red"}).json()] == [
        "Acme Legal"
    ]
    assert api.get("/clients", params={"health": "green"}).json() == []

    # Contact counts from client-since when nothing was ever logged.
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE accounts SET client_since = :d WHERE id = :a"),
            {"d": TODAY - timedelta(days=61), "a": account_id},
        )
    reasons = [r["text"] for r in api.get("/clients").json()[0]["reasons"]]
    assert "No contact since becoming a client for 61 days" in reasons

    # Logging a call is contact.
    logged = api.send(
        "POST",
        "/activities",
        json={
            "account_id": account_id,
            "kind": "call",
            "summary": "Weekly check-in",
            "call_outcome": "connected",
        },
    )
    assert logged.status_code == 201, logged.text
    reasons = [r["text"] for r in api.get("/clients").json()[0]["reasons"]]
    assert not any("No contact" in r for r in reasons)


def test_the_retention_engine_raises_a_risk_once(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    account_id, project_id = client(engine, api, admin)
    first = api.send("POST", "/clients/health-check").json()
    assert first == {"assessed": 1, "changed": 1, "risks_raised": 0}  # the first Green is recorded
    assert api.send("POST", "/clients/health-check").json()["changed"] == 0

    api.send("PATCH", f"/projects/{project_id}", json={"status": "at_risk"})
    turned = api.send("POST", "/clients/health-check").json()
    assert turned == {"assessed": 1, "changed": 1, "risks_raised": 1}
    assert risk_tasks(engine, account_id) == [
        ("Client risk detected: talk to Acme Legal", str(admin))
    ]
    events = [e["summary"] for e in api.get(f"/accounts/{account_id}/timeline").json()]
    assert "Client risk detected: Portal is marked at risk." in events
    assert "Client health: Green to Red (Portal is marked at risk)." in events

    # Back to Green, then Red again while the first task is still open: no second task.
    api.send("PATCH", f"/projects/{project_id}", json={"status": "active"})
    assert api.send("POST", "/clients/health-check").json()["changed"] == 1
    api.send("PATCH", f"/projects/{project_id}", json={"status": "at_risk"})
    again = api.send("POST", "/clients/health-check").json()
    assert again == {"assessed": 1, "changed": 1, "risks_raised": 0}
    assert len(risk_tasks(engine, account_id)) == 1

    history = api.get(f"/accounts/{account_id}/health").json()["history"]
    assert [h["colour"] for h in history] == ["red", "green", "red", "green"]
    assert history[0]["reasons"] == [{"level": "red", "text": "Portal is marked at risk"}]


def test_negative_feedback_raises_a_risk_at_once(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    account_id, _ = client(engine, api, admin)
    said = api.send(
        "POST",
        f"/accounts/{account_id}/feedback",
        json={"sentiment": "negative", "note": "Releases keep slipping"},
    )
    assert said.status_code == 201, said.text
    assert (
        said.json()["recorded_by"] == "Ada Admin"
        and said.json()["received_on"] == TODAY.isoformat()
    )
    found = api.get(f"/accounts/{account_id}/health").json()
    assert found["current"]["health"] == "red"
    assert found["current"]["latest_feedback"] == "negative"
    assert [f["note"] for f in found["feedback"]] == ["Releases keep slipping"]
    assert len(risk_tasks(engine, account_id)) == 1

    future = api.send(
        "POST",
        f"/accounts/{account_id}/feedback",
        json={"sentiment": "positive", "received_on": (TODAY + timedelta(days=1)).isoformat()},
    )
    assert future.status_code == 422
    api.send(
        "POST",
        f"/accounts/{account_id}/feedback",
        json={"sentiment": "positive", "note": "Much better"},
    )
    assert api.get(f"/accounts/{account_id}/health").json()["current"]["health"] == "green"


def test_feedback_is_for_clients(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    from tests.integration.test_leads import account

    prospect = account(engine, "Prospect Co", domain="prospect.test", owner=admin)
    refused = api.send("POST", f"/accounts/{prospect}/feedback", json={"sentiment": "positive"})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "not_a_client"
    assert api.get(f"/accounts/{prospect}/health").json() == {
        "current": None,
        "history": [],
        "feedback": [],
    }


def test_ending_a_client_relationship(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    account_id, project_id = client(engine, api, admin)
    blocked = api.send(
        "POST", f"/accounts/{account_id}/end-client", json={"reason": "Contract ended"}
    )
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "open_projects"

    api.send("PATCH", f"/projects/{project_id}", json={"status": "completed"})
    ended = api.send(
        "POST", f"/accounts/{account_id}/end-client", json={"reason": "Contract ended"}
    )
    assert ended.status_code == 204
    acc = api.get(f"/accounts/{account_id}").json()
    assert acc["account_type"] == "former_customer" and acc["client_since"] == TODAY.isoformat()
    assert api.get("/clients").json() == []
    assert api.send("POST", "/clients/health-check").json()["assessed"] == 0
    events = [e["summary"] for e in api.get(f"/accounts/{account_id}/timeline").json()]
    assert "No longer a client: Contract ended" in events


def test_who_sees_and_checks_client_health(
    engine: Engine, api: ApiClient, admin: uuid.UUID, make_api: Callable[[], ApiClient]
) -> None:
    account_id, project_id = client(engine, api, admin)
    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    assert seller.get("/clients").json() == []  # Ada's client is not Sam's
    assert seller.get(f"/accounts/{account_id}/health").status_code == 404
    assert seller.send("POST", "/clients/health-check").status_code == 403

    api.send("PATCH", f"/projects/{project_id}", json={"status": "at_risk"})
    board = api.get("/reports/management").json()
    table = next(t for t in board["tables"] if t["key"] == "clients_at_risk")
    assert table["rows"] == [
        {
            "label": "Acme Legal",
            "values": ["Red", "Portal is marked at risk", "Ada Admin"],
            "href": f"/accounts/{account_id}?tab=client",
        }
    ]
    views = [v["name"] for v in api.get("/saved-views").json()]
    assert views[-1] == "At-Risk Clients"
