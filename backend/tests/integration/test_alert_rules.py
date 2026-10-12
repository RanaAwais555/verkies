"""Slice 6.3: alert rules raise flags and create follow-up tasks; in-app notifications."""

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from app.providers.storage import LocalStorage
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_monitoring import (
    BOARD,
    SERVICES,
    FakeSource,
    board,
    check,
    html,
    site,
    watched_site,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def admin(engine: Engine, api: ApiClient) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    return user_id


@pytest.fixture
def no_rules(engine: Engine) -> None:
    """Start without the rules migration 0028 seeds, so each test sets its own."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM alert_rules"))


def rule(api: ApiClient, **body: object) -> dict[str, object]:
    response = api.send("POST", "/monitoring/rules", json=body)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def changed_site() -> dict[str, tuple[int, str, str]]:
    web = site()
    web[SERVICES] = (
        200,
        "text/html",
        html("<h1>Services</h1><p>We now offer corporate immigration and sponsor licences.</p>"),
    )
    return web


def test_the_starting_rules_follow_the_master_context(
    engine: Engine, api: ApiClient, admin: uuid.UUID, tmp_path: Path
) -> None:
    assert {(r["name"], r["action"]) for r in api.get("/monitoring/rules").json()} == {
        ("Funding, acquisition or expansion", "opportunity_detected"),
        ("New service or product launch", "opportunity_detected"),
        ("Leadership change", "requires_review"),
        ("Services or pricing changed on the website", "requires_review"),
        ("Hiring for product or engineering", "task"),
    }
    storage = LocalStorage(tmp_path)
    acme = watched_site(engine, admin, storage)
    result = check(acme, FakeSource(changed_site() | board("CTO")), storage)
    assert result.flagged == 2 and result.tasks == 1
    assert api.get(f"/accounts/{acme}").json()["attention"] == "requires_review"


@pytest.mark.usefixtures("no_rules")
def test_managing_rules(
    engine: Engine, api: ApiClient, admin: uuid.UUID, make_api: Callable[[], ApiClient]
) -> None:
    created = rule(api, name=" Funding ", signals=["funding"], action="opportunity_detected")
    assert created["name"] == "Funding" and created["active"] is True
    bad = api.send(
        "POST", "/monitoring/rules", json={"name": "x", "signals": ["vibes"], "action": "task"}
    )
    assert bad.status_code == 422 and "vibes" in bad.text
    empty = api.send("POST", "/monitoring/rules", json={"name": "Everything", "action": "task"})
    assert empty.status_code == 422
    off = api.send("PATCH", f"/monitoring/rules/{created['id']}", json={"active": False}).json()
    assert off["active"] is False
    choices = api.get("/monitoring/rule-choices").json()
    assert {"key": "funding", "label": "Raised funding"} in choices["signals"]

    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    assert [r["name"] for r in seller.get("/monitoring/rules").json()] == ["Funding"]
    assert seller.send("DELETE", f"/monitoring/rules/{created['id']}").status_code == 403
    assert api.send("DELETE", f"/monitoring/rules/{created['id']}").status_code == 204
    assert api.get("/monitoring/rules").json() == []


@pytest.mark.usefixtures("no_rules")
def test_rules_flag_alerts_and_create_one_task(
    engine: Engine, api: ApiClient, admin: uuid.UUID, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    acme = watched_site(engine, admin, storage)
    api.send("PUT", f"/accounts/{acme}/watch")
    rule(api, name="Product hiring", signals=["product_hiring"], action="requires_review")
    rule(
        api,
        name="Services changed",
        kinds=["website"],
        topics=["services"],
        action="opportunity_detected",
    )
    rule(
        api,
        name="Hiring follow-up",
        signals=["product_hiring", "cto_hiring"],
        action="task",
        task_title="Follow up on hiring at {account}",
    )
    rule(api, name="Switched off", kinds=["website"], action="task", active=False)

    web = changed_site() | board("Head of Product")
    result = check(acme, FakeSource(web), storage)
    assert result.flagged == 2 and result.tasks == 1
    alerts = {a["title"]: a for a in api.get("/monitoring/alerts").json()}
    hiring, services = alerts["Head of Product"], alerts["Services page changed"]
    assert hiring["raised"] == "requires_review"
    assert [r["name"] for r in hiring["rules"]] == ["Product hiring", "Hiring follow-up"]
    assert services["raised"] == "opportunity_detected" and services["task_id"] is None
    assert api.get(f"/accounts/{acme}").json()["attention"] == "opportunity_detected"
    assert api.get("/monitoring/watched").json()[0]["attention"] == "opportunity_detected"
    assert len(api.get("/monitoring/alerts", params={"raised": True}).json()) == 2

    tasks = api.get(f"/accounts/{acme}").json()["tasks"]
    (task,) = [t for t in tasks if t["title"] == "Follow up on hiring at Acme Legal"]
    assert hiring["task_id"] == task["id"]
    with engine.connect() as conn:
        owner, description = conn.execute(
            text("SELECT owner_id, description FROM tasks WHERE id = :t"), {"t": task["id"]}
        ).one()
    assert owner == admin and "Head of Product" in description and BOARD not in description

    events = [e["summary"] for e in api.get(f"/accounts/{acme}/timeline").json()]
    assert any(e.startswith("Opportunity Detected: ") for e in events)

    titles = [n["title"] for n in api.get("/notifications").json()]
    assert sorted(titles) == [
        "Acme Legal: Opportunity Detected",
        "New task: Follow up on hiring at Acme Legal",
    ]
    assert api.get("/notifications/count").json() == {"unread": 2}

    # A second hiring alert while the task is still open joins it; no second task.
    again = check(acme, FakeSource(changed_site() | board("Head of Product", "CTO")), storage)
    assert again.new == 1 and again.tasks == 0 and again.flagged == 0
    cto = next(a for a in api.get("/monitoring/alerts").json() if a["title"] == "CTO")
    assert cto["task_id"] == task["id"] and cto["raised"] is None

    # Reviewing the flagged alerts clears the account's flag.
    for alert in api.get("/monitoring/alerts", params={"raised": True}).json():
        api.send("POST", f"/monitoring/alerts/{alert['id']}/review")
    assert api.get(f"/accounts/{acme}").json()["attention"] is None


@pytest.mark.usefixtures("no_rules")
def test_notifications_can_be_read_and_switched_off(
    engine: Engine, api: ApiClient, admin: uuid.UUID, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    acme = watched_site(engine, admin, storage)
    api.send("PUT", f"/accounts/{acme}/watch")
    prefs = api.send("PUT", "/notifications/preferences", json={"off": ["monitoring_alert"]})
    assert {p["kind"]: p["on"] for p in prefs.json()} == {
        "monitoring_alert": False,
        "rule_task": True,
    }
    assert api.send("PUT", "/notifications/preferences", json={"off": ["spam"]}).status_code == 422

    check(acme, FakeSource(changed_site()), storage)
    assert api.get("/notifications").json() == []  # switched off: nothing created

    api.send("PUT", "/notifications/preferences", json={"off": []})
    web = site()
    web[SERVICES] = (200, "text/html", html("<h1>Services</h1><p>Now also family visas.</p>"))
    check(acme, FakeSource(web), storage)
    (note,) = api.get("/notifications").json()
    assert note["title"] == "Acme Legal: 1 new alert" and note["link"] == f"/accounts/{acme}"
    assert api.send("POST", f"/notifications/{note['id']}/read").json()["read"] is True
    assert api.get("/notifications", params={"unread": True}).json() == []
    assert api.send("POST", "/notifications/read-all").status_code == 204
    assert api.get("/notifications/count").json() == {"unread": 0}
