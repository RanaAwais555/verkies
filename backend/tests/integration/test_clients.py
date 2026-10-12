"""Slice 4.1: converting a won deal to a client, and projects with milestones, risks and tasks."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text

from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_deals import stages
from tests.integration.test_leads import account, opportunity

pytestmark = pytest.mark.integration

TODAY = datetime.now(UTC).date()


@pytest.fixture
def admin(engine: Engine, api: ApiClient) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    return user_id


def won_deal(engine: Engine, api: ApiClient, owner: uuid.UUID, name: str = "Acme Legal") -> dict:  # type: ignore[type-arg]
    acme = account(engine, name, domain=f"{name.split()[0].lower()}.test", owner=owner)
    opp = opportunity(engine, acme, "crm")
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE opportunities SET service_id ="
                " (SELECT id FROM services WHERE key = 'web_dev') WHERE id = :o"
            ),
            {"o": opp},
        )
    deal = api.send("POST", "/deals", json={"opportunity_id": str(opp), "value": "18000"}).json()
    moved = api.send(
        "POST", f"/deals/{deal['id']}/move", json={"stage_id": stages(api, "new_business")["won"]}
    )
    assert moved.status_code == 200, moved.text
    return moved.json()  # type: ignore[no-any-return]


def test_converting_a_won_deal_keeps_the_account_and_starts_a_project(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    manager = make_user(engine, "mo@verkies.test", ["project_manager"], name="Mo Manager")
    deal = won_deal(engine, api, admin)
    start = TODAY + timedelta(days=3)

    converted = api.send(
        "POST",
        f"/deals/{deal['id']}/convert",
        json={
            "account_manager_id": str(manager),
            "project": {
                "start_date": start.isoformat(),
                "target_date": (start + timedelta(days=60)).isoformat(),
                "milestones": [
                    {
                        "name": "Discovery signed off",
                        "due_date": (start + timedelta(days=10)).isoformat(),
                    },
                    {"name": "Launch"},
                ],
            },
        },
    )
    assert converted.status_code == 200, converted.text
    body = converted.json()
    assert body["account_id"] == deal["account_id"]  # the same account, never a copy
    assert body["became_client"] and body["account_type"] == "customer"

    acc = api.get(f"/accounts/{deal['account_id']}").json()
    assert acc["account_type"] == "customer"
    assert acc["client_since"] == TODAY.isoformat()
    assert acc["account_manager"]["name"] == "Mo Manager"
    assert len(acc["opportunities"]) == 1  # history stays where it was

    project = api.get(f"/projects/{body['project_id']}").json()
    assert project["name"] == deal["name"]  # defaults to the deal's name
    assert project["deal"]["id"] == deal["id"] and project["deal"]["value"] == 18000
    assert project["service_name"] == "Web Development"  # from the opportunity
    assert project["owner"]["name"] == "Mo Manager"
    assert project["status"] == "not_started"
    assert [m["name"] for m in project["milestones"]] == ["Discovery signed off", "Launch"]
    assert [t["title"] for t in project["tasks"]] == [f"Kick off {deal['name']}"]
    assert project["tasks"][0]["due_at"].startswith(start.isoformat())
    assert project["requires_attention"] == []

    board = api.get("/deals", params={"status": "won"}).json()
    assert board[0]["project_id"] == body["project_id"]

    events = [e["event_type"] for e in api.get(f"/accounts/{deal['account_id']}/timeline").json()]
    assert {"account.converted", "project.created", "task.created"} <= set(events)
    actions = {e["action"] for e in api.get(f"/accounts/{deal['account_id']}/audit").json()}
    assert {"account.converted", "project.created"} <= actions

    again = api.send("POST", f"/deals/{deal['id']}/convert", json={"project": {}})
    assert again.status_code == 409
    assert again.json()["error"]["details"]["project_id"] == body["project_id"]
    nothing = api.send("POST", f"/deals/{deal['id']}/convert", json={})
    assert nothing.status_code == 409


def test_only_won_deals_convert_and_competitors_never(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    acme = account(engine, "Open Co", domain="open.test", owner=admin)
    opp = opportunity(engine, acme, "crm")
    deal = api.send("POST", "/deals", json={"opportunity_id": str(opp)}).json()
    refused = api.send("POST", f"/deals/{deal['id']}/convert", json={})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "deal_not_won"

    won = won_deal(engine, api, admin, "Rival Studio")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE accounts SET account_type = 'competitor' WHERE id = :a"),
            {"a": won["account_id"]},
        )
    rival = api.send("POST", f"/deals/{won['id']}/convert", json={})
    assert rival.status_code == 422 and rival.json()["error"]["code"] == "not_convertible"

    prospect = api.send("POST", "/projects", json={"account_id": str(acme), "name": "Not yet"})
    assert prospect.status_code == 422 and prospect.json()["error"]["code"] == "not_a_client"


def test_a_former_client_keeps_its_first_client_date(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    deal = won_deal(engine, api, admin)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE accounts SET account_type = 'former_customer', client_since = '2023-04-01'"
                " WHERE id = :a"
            ),
            {"a": deal["account_id"]},
        )
    body = api.send("POST", f"/deals/{deal['id']}/convert", json={}).json()
    assert body["became_client"] and body["project_id"] is None
    acc = api.get(f"/accounts/{deal['account_id']}").json()
    assert acc["account_type"] == "customer" and acc["client_since"] == "2023-04-01"


def test_working_a_project(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    deal = won_deal(engine, api, admin)
    project_id = api.send(
        "POST",
        f"/deals/{deal['id']}/convert",
        json={"project": {"name": "Client portal"}, "kickoff_task": False},
    ).json()["project_id"]
    project = api.get(f"/projects/{project_id}").json()
    assert project["tasks"] == [] and project["owner"]["id"] == str(admin)

    late = (TODAY - timedelta(days=2)).isoformat()
    added = api.send(
        "POST", f"/projects/{project_id}/milestones", json={"name": "Designs", "due_date": late}
    )
    assert added.status_code == 201
    milestone = added.json()["milestones"][0]
    assert milestone["overdue"]
    risk = api.send(
        "POST",
        f"/projects/{project_id}/risks",
        json={"description": "Their API has no sandbox", "severity": "high"},
    ).json()
    task = api.send(
        "POST",
        "/tasks",
        json={
            "account_id": deal["account_id"],
            "project_id": project_id,
            "title": "Ask for API keys",
            "due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    assert task.status_code == 201 and task.json()["project_id"] == project_id

    project = api.get(f"/projects/{project_id}").json()
    assert project["requires_attention"] == [
        "1 milestone overdue",
        "1 high risk open",
        "1 overdue task",
    ]
    assert project["open_risks"] == 1 and project["overdue_tasks"] == 1
    listed = api.get("/projects").json()
    assert [p["id"] for p in listed] == [project_id]

    done = api.send("PATCH", f"/milestones/{milestone['id']}", json={"done": True}).json()
    assert done["done"] and not done["overdue"]
    resolved = api.send(
        "PATCH", f"/risks/{risk['id']}", json={"resolved": True, "resolution": "Mock server agreed"}
    ).json()
    assert resolved["resolved"] and resolved["resolution"] == "Mock server agreed"

    bad_dates = api.send(
        "PATCH",
        f"/projects/{project_id}",
        json={"start_date": "2026-05-01", "target_date": "2026-04-01"},
    )
    assert bad_dates.status_code == 422 and bad_dates.json()["error"]["code"] == "invalid_dates"

    updated = api.send("PATCH", f"/projects/{project_id}", json={"status": "active"}).json()
    assert updated["status"] == "active" and updated["completed_on"] is None
    completed = api.send("PATCH", f"/projects/{project_id}", json={"status": "completed"}).json()
    assert completed["completed_on"] == TODAY.isoformat()
    assert completed["requires_attention"] == []  # closed projects need nothing
    assert api.get("/projects").json() == []
    assert [p["id"] for p in api.get("/projects", params={"status": "closed"}).json()] == [
        project_id
    ]

    events = [e["summary"] for e in api.get(f"/accounts/{deal['account_id']}/timeline").json()]
    assert "Milestone reached on Client portal: Designs." in events
    assert "Project Client portal: Active to Completed." in events
    assert any(e.startswith("High risk raised on Client portal") for e in events)

    gone = api.send("DELETE", f"/milestones/{milestone['id']}")
    assert gone.status_code == 204
    assert api.get(f"/projects/{project_id}").json()["milestones"] == []


def test_an_existing_client_can_start_another_project(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    deal = won_deal(engine, api, admin)
    api.send("POST", f"/deals/{deal['id']}/convert", json={})
    created = api.send(
        "POST",
        "/projects",
        json={
            "account_id": deal["account_id"],
            "name": "SEO retainer",
            "start_date": "2026-11-01",
            "milestones": [{"name": "Audit", "due_date": "2026-11-15"}],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["deal"] is None and created.json()["owner"] is None
    assert created.json()["requires_attention"] == ["no project owner"]

    manager = make_user(engine, "mo@verkies.test", ["project_manager"], name="Mo Manager")
    set_manager = api.send(
        "PUT",
        f"/accounts/{deal['account_id']}/account-manager",
        json={"account_manager_id": str(manager)},
    )
    assert set_manager.status_code == 204
    assert api.get(f"/accounts/{deal['account_id']}").json()["account_manager"]["id"] == str(
        manager
    )


def test_people_see_only_projects_on_accounts_they_can_see(
    engine: Engine,
    api: ApiClient,
    admin: uuid.UUID,
    make_api: Callable[[], ApiClient],
) -> None:
    deal = won_deal(engine, api, admin)
    project_id = api.send("POST", f"/deals/{deal['id']}/convert", json={"project": {}}).json()[
        "project_id"
    ]

    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    assert seller.get("/projects").json() == []
    assert seller.get(f"/projects/{project_id}").status_code == 404
    hidden = seller.send("POST", f"/projects/{project_id}/risks", json={"description": "x"})
    assert hidden.status_code == 404
    assert seller.send("POST", f"/deals/{deal['id']}/convert", json={}).status_code == 404

    make_user(engine, "pat@verkies.test", ["project_manager"], name="Pat PM")
    pm = make_api()
    pm.login("pat@verkies.test")
    assert [p["id"] for p in pm.get("/projects").json()] == [project_id]
    assert (
        pm.send("PATCH", f"/projects/{project_id}", json={"status": "planning"}).status_code == 200
    )


def test_merging_accounts_moves_projects(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    deal = won_deal(engine, api, admin)
    project_id = api.send("POST", f"/deals/{deal['id']}/convert", json={"project": {}}).json()[
        "project_id"
    ]
    keep = account(engine, "Acme Legal Ltd", domain="acmelegal.test", owner=admin)
    merged = api.send(
        "POST",
        f"/accounts/{keep}/merge",
        json={"merge_id": deal["account_id"], "reason": "Same firm"},
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["moved"]["projects"] == 1
    assert api.get(f"/projects/{project_id}").json()["account_id"] == str(keep)
