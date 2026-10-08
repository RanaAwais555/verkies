"""Approve and reject end to end: research a fixture site, review it, and check the Account,
Lead, Opportunity, Contacts, Task, timeline and audit trail that approval creates."""

import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.config import Settings, get_settings
from app.main import create_app
from app.prospects import service as prospects
from app.research.router import get_enqueuer
from tests.fixtures.sites import (
    AGENCY,
    IMMIGRATION_ABOUT,
    IMMIGRATION_CONTACT,
    IMMIGRATION_HOME,
    IMMIGRATION_TEAM,
)
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_research import run_pipeline

pytestmark = pytest.mark.integration

SITES = {
    "harbour.test": {
        "/": IMMIGRATION_HOME,
        "/contact/": IMMIGRATION_CONTACT,
        "/our-team/": IMMIGRATION_TEAM,
        "/about-us/": IMMIGRATION_ABOUT,
    },
    "pixelforge.test": {"/": AGENCY[0][0].html},
}
HOSTS = tuple(SITES)
Research = Callable[..., str]


@pytest.fixture
def site_port() -> Iterator[int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            host = (self.headers.get("Host") or "").split(":")[0]
            page = SITES.get(host, {}).get(self.path)
            if page is None:
                self.send_response(404)
                self.end_headers()
                return
            body = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


@pytest.fixture
def settings(site_port: int, tmp_path: Path) -> Settings:
    return get_settings().model_copy(
        update={
            "crawl_allowed_ports": [site_port, 80, 443],
            "fetch_private_allowlist": ["127.0.0.0/8"],
            "crawl_min_interval_seconds": 0.0,
            "storage_dir": str(tmp_path / "storage"),
        }
    )


@pytest.fixture
def client(engine: Engine, settings: Settings) -> Iterator[ApiClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_enqueuer] = lambda: lambda _run_id: None
    with TestClient(app) as http:
        yield ApiClient(http)


@pytest.fixture
def researched(client: ApiClient, engine: Engine, settings: Settings, site_port: int) -> Research:
    """Research a site as a researcher; returns the run id. Leaves the client signed out."""

    def go(host: str = "harbour.test") -> str:
        if not getattr(go, "user", None):
            make_user(engine, "researcher@verkies.test", ["researcher"])
            go.user = True  # type: ignore[attr-defined]
        client.login("researcher@verkies.test")
        response = client.send(
            "POST", "/research-runs", json={"url": f"http://{host}:{site_port}/"}
        )
        assert response.status_code == 202, response.text
        run_id = response.json()["id"]
        run_pipeline(uuid.UUID(run_id), settings, render=False, hosts=HOSTS)
        assert client.get(f"/research-runs/{run_id}").json()["status"] == "completed"
        client.send("POST", "/auth/logout")
        return str(run_id)

    return go


def _manager(client: ApiClient, engine: Engine, email: str = "manager@verkies.test") -> uuid.UUID:
    user_id = make_user(engine, email, ["sales_manager"], name="Mia Manager")
    client.login(email)
    return user_id


def _count(engine: Engine, sql: str, **params: object) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(sql), params).scalar_one())


def test_approval_creates_the_crm_records_in_one_go(
    client: ApiClient, engine: Engine, researched: Research, site_port: int
) -> None:
    run_id = researched()
    manager_id = _manager(client, engine)

    queue = client.get("/prospects").json()
    assert [q["run_id"] for q in queue] == [run_id]
    item = queue[0]
    assert item["qualifies"] and not item["hard_reject"] and item["priority_band"] == "high"
    assert item["company"] == "Harbour Immigration Ltd" and item["possible_duplicates"] == []
    assert item["next_action"]

    response = client.send("POST", f"/prospects/{run_id}/approve", json={})
    assert response.status_code == 200, response.text
    approval = response.json()
    assert approval["created_account"] and approval["opportunity_id"]
    assert len(approval["contact_ids"]) == 2

    account = client.get(f"/accounts/{approval['account_id']}").json()
    assert account["name"] == "Harbour Immigration Ltd"
    assert account["primary_domain"] == "harbour.test" and account["domains"] == ["harbour.test"]
    assert account["account_type"] == "qualified_prospect"
    assert account["hq_country"] == "GB" and account["hq_city"] == "London"
    assert account["owner"] == {"id": str(manager_id), "name": "Mia Manager"}
    assert account["priority_band"] == "high" and account["scores"]["intent_score"] is None
    assert account["latest_brief_run_id"] == run_id
    assert [r["review_status"] for r in account["research_runs"]] == ["approved"]

    (lead,) = account["leads"]
    assert lead["status"] == "qualified" and lead["research_run_id"] == run_id
    assert lead["owner"]["id"] == str(manager_id) and lead["priority_band"] == "high"

    (opportunity,) = account["opportunities"]
    assert opportunity["id"] == approval["opportunity_id"]
    assert opportunity["requires_attention"] == []
    assert opportunity["next_action_task_id"] == approval["task_id"]
    assert opportunity["name"] == "Website rebuild: Harbour Immigration Ltd"
    assert "copyright still says 2017" in opportunity["problem"]  # the strongest problem found

    contacts = {c["name"]: c for c in account["contacts"]}
    assert contacts["Amelia Hart"]["decision_maker_role"] == "decision_maker"
    assert contacts["Daniel Okafor"]["decision_maker_role"] == "operations_buyer"
    for contact in contacts.values():
        assert contact["email"] is None and contact["phone"] is None  # never invented
        assert contact["source_url"] == f"http://harbour.test:{site_port}/our-team/"
        assert contact["verification_status"] == "unverified"

    (task,) = account["tasks"]
    assert task["id"] == approval["task_id"] and task["status"] == "open"
    assert task["owner_id"] == str(manager_id) and task["title"] == item["next_action"]
    due = datetime.fromisoformat(task["due_at"])
    assert timedelta(days=2) <= due - datetime.now(UTC) <= timedelta(days=4, minutes=1)
    assert due.weekday() < 5
    assert account["next_activity_at"] == task["due_at"] and account["open_tasks"] == 1

    events = client.get(f"/accounts/{approval['account_id']}/timeline").json()
    assert [e["event_type"] for e in reversed(events)] == [
        "account.created",
        "research.completed",
        "lead.qualified",
        "opportunity.created",
        "contact.added",
        "contact.added",
        "task.created",
    ]
    assert events[0]["actor"]["name"] == "Mia Manager"

    actions = {e["action"] for e in client.get(f"/accounts/{approval['account_id']}/audit").json()}
    assert {"research.started", "prospect.approved", "account.created"} <= actions

    # The research now belongs to the account (append-only rows, account_id set once).
    for table in ("evidence", "observations", "claims", "score_snapshots"):
        unattached = _count(
            engine,
            f"SELECT count(*) FROM {table} WHERE research_run_id = :r AND account_id IS NULL",  # noqa: S608
            r=run_id,
        )
        assert unattached == 0, table
    assert client.get("/prospects").json() == []  # off the queue

    again = client.send("POST", f"/prospects/{run_id}/approve", json={})
    assert again.status_code == 409 and "already approved" in again.json()["error"]["message"]
    assert _count(engine, "SELECT count(*) FROM leads") == 1


def test_research_on_a_known_domain_attaches_to_its_account(
    client: ApiClient, engine: Engine, researched: Research
) -> None:
    first = researched()
    _manager(client, engine)
    account_id = client.send("POST", f"/prospects/{first}/approve", json={}).json()["account_id"]
    client.send("POST", "/auth/logout")

    second = researched()
    client.login("manager@verkies.test")
    (item,) = client.get("/prospects").json()
    assert item["possible_duplicates"][0]["match"] == "domain"
    elsewhere = client.send(
        "POST", f"/prospects/{second}/approve", json={"account_id": str(uuid.uuid4())}
    )
    assert elsewhere.status_code == 409 and elsewhere.json()["error"]["code"] == "domain_taken"

    response = client.send("POST", f"/prospects/{second}/approve", json={})
    assert response.status_code == 200, response.text
    assert response.json()["account_id"] == account_id and not response.json()["created_account"]
    assert response.json()["contact_ids"] == []  # the same two people are not added twice
    account = client.get(f"/accounts/{account_id}").json()
    assert len(account["leads"]) == 2 and len(account["contacts"]) == 2
    assert _count(engine, "SELECT count(*) FROM accounts") == 1


def test_possible_duplicate_needs_a_decision(
    client: ApiClient, engine: Engine, researched: Research
) -> None:
    run_id = researched()
    existing = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, name, primary_domain, account_type, created_at,"
                " updated_at) VALUES (:id, 'Harbour Immigration', 'harbour-immigration.test',"
                " 'prospect', now(), now())"
            ),
            {"id": existing},
        )
        conn.execute(
            text(
                "INSERT INTO account_domains (id, account_id, domain, is_primary, created_at)"
                " VALUES (gen_random_uuid(), :id, 'harbour-immigration.test', true, now())"
            ),
            {"id": existing},
        )
    _manager(client, engine)

    blocked = client.send("POST", f"/prospects/{run_id}/approve", json={})
    assert blocked.status_code == 409
    error = blocked.json()["error"]
    assert error["code"] == "possible_duplicate"
    (dup,) = error["details"]["possible_duplicates"]
    assert dup["account_id"] == str(existing) and dup["match"] == "name"

    merged = client.send("POST", f"/prospects/{run_id}/approve", json={"account_id": str(existing)})
    assert merged.status_code == 200, merged.text
    assert merged.json()["account_id"] == str(existing) and not merged.json()["created_account"]
    account = client.get(f"/accounts/{existing}").json()
    assert sorted(account["domains"]) == ["harbour-immigration.test", "harbour.test"]
    assert account["account_type"] == "qualified_prospect"  # promoted from prospect
    events = [e["event_type"] for e in client.get(f"/accounts/{existing}/timeline").json()]
    assert "account.created" not in events and "lead.qualified" in events


def test_confirming_a_new_company_despite_similar_names(
    client: ApiClient, engine: Engine, researched: Research
) -> None:
    run_id = researched()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, name, account_type, created_at, updated_at)"
                " VALUES (gen_random_uuid(), 'Harbour Immigration Limited', 'prospect',"
                " now(), now())"
            )
        )
    _manager(client, engine)
    response = client.send(
        "POST", f"/prospects/{run_id}/approve", json={"create_new_account": True}
    )
    assert response.status_code == 200 and response.json()["created_account"]
    assert _count(engine, "SELECT count(*) FROM accounts") == 2


def test_rejection_is_audited_off_the_queue_and_still_searchable(
    client: ApiClient, engine: Engine, researched: Research
) -> None:
    run_id = researched()
    _manager(client, engine)
    response = client.send(
        "POST",
        f"/prospects/{run_id}/reject",
        json={"reason": "wrong_icp", "note": "Too small for us", "suppress": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["review_status"] == "rejected"

    assert client.get("/prospects").json() == []
    found = client.get("/research-runs", params={"review_status": "rejected", "q": "harbour"})
    (run,) = found.json()
    assert run["id"] == run_id and run["rejection_reason"] == "wrong_icp"
    assert run["rejection_note"] == "Too small for us" and run["account_id"] is None
    assert client.get("/research-runs", params={"q": "nomatch%"}).json() == []

    entries = client.get("/audit", params={"object_id": run_id}).json()["items"]
    rejected = next(e for e in entries if e["action"] == "prospect.rejected")
    assert rejected["new_value"]["rejection_reason"] == "wrong_icp"
    assert rejected["reason"] == "Too small for us"
    assert _count(engine, "SELECT count(*) FROM suppressions WHERE value = 'harbour.test'") == 1
    assert _count(engine, "SELECT count(*) FROM accounts") == 0
    assert _count(engine, "SELECT count(*) FROM leads") == 0

    twice = client.send("POST", f"/prospects/{run_id}/reject", json={"reason": "duplicate"})
    assert twice.status_code == 409
    client.send("POST", "/auth/logout")

    # Researching the suppressed domain again cannot be approved.
    again = researched()
    client.login("manager@verkies.test")
    (item,) = client.get("/prospects").json()
    assert item["hard_reject"] and item["recommended_rejection"] == "suppressed_account"
    blocked = client.send(
        "POST", f"/prospects/{again}/approve", json={"override_reason": "they asked us to call"}
    )
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "suppressed"


def test_approving_against_the_engines_needs_a_reason(
    client: ApiClient, engine: Engine, researched: Research
) -> None:
    run_id = researched("pixelforge.test")
    _manager(client, engine)
    (item,) = client.get("/prospects").json()
    assert item["hard_reject"] and item["recommended_rejection"] == "competitor"

    refused = client.send("POST", f"/prospects/{run_id}/approve", json={})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "override_required"
    short = client.send("POST", f"/prospects/{run_id}/approve", json={"override_reason": "ok"})
    assert short.status_code == 422

    reason = "Partnership talk: they want a white-label build partner"
    approved = client.send("POST", f"/prospects/{run_id}/approve", json={"override_reason": reason})
    assert approved.status_code == 200, approved.text
    entries = client.get("/audit", params={"object_id": run_id}).json()["items"]
    decision = next(e for e in entries if e["action"] == "prospect.approved")
    assert decision["reason"] == reason and decision["new_value"]["engine_qualified"] is False


def test_a_failure_part_way_through_leaves_nothing_behind(
    client: ApiClient, engine: Engine, researched: Research, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = researched()
    _manager(client, engine)

    async def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated failure while adding contacts")

    monkeypatch.setattr(prospects, "_contacts", broken)
    with pytest.raises(RuntimeError):
        client.send("POST", f"/prospects/{run_id}/approve", json={})

    for table in (
        "accounts",
        "account_domains",
        "leads",
        "opportunities",
        "tasks",
        "timeline_events",
    ):
        assert _count(engine, f"SELECT count(*) FROM {table}") == 0, table  # noqa: S608
    assert _count(engine, "SELECT count(*) FROM evidence WHERE account_id IS NOT NULL") == 0
    assert _count(engine, "SELECT count(*) FROM research_runs WHERE review_status = 'pending'") == 1

    monkeypatch.undo()
    assert client.send("POST", f"/prospects/{run_id}/approve", json={}).status_code == 200


def test_tasks_attention_and_visibility(
    client: ApiClient, engine: Engine, researched: Research
) -> None:
    run_id = researched()
    seller_a = make_user(engine, "a@verkies.test", ["salesperson"], name="Ana Seller")
    make_user(engine, "b@verkies.test", ["salesperson"], name="Ben Seller")
    make_user(engine, "viewer@verkies.test", ["viewer"])

    client.login("researcher@verkies.test")
    assert client.get("/prospects").status_code == 403  # researchers do not review
    client.send("POST", "/auth/logout")

    client.login("a@verkies.test")
    approval = client.send("POST", f"/prospects/{run_id}/approve", json={}).json()
    account_id, task_id = approval["account_id"], approval["task_id"]
    (mine,) = client.get("/tasks").json()
    assert mine["id"] == task_id and mine["account_name"] == "Harbour Immigration Ltd"
    assert mine["owner_name"] == "Ana Seller"
    assert client.get("/opportunities/requires-attention").json() == []

    later = (datetime.now(UTC) + timedelta(days=7)).replace(microsecond=0)
    moved = client.send("PATCH", f"/tasks/{task_id}", json={"due_at": later.isoformat()})
    assert moved.status_code == 200 and datetime.fromisoformat(moved.json()["due_at"]) == later
    done = client.send("POST", f"/tasks/{task_id}/complete", json={"note": "Sent the note"})
    assert done.status_code == 200 and done.json()["status"] == "done"
    assert client.send("POST", f"/tasks/{task_id}/complete", json={}).status_code == 409
    assert client.get("/tasks").json() == []

    (attention,) = client.get("/opportunities/requires-attention").json()
    assert attention["id"] == approval["opportunity_id"]
    assert attention["requires_attention"] == ["next action is closed; set a new one"]
    account = client.get(f"/accounts/{account_id}").json()
    assert account["next_activity_at"] is None and account["open_tasks"] == 0
    events = [e["event_type"] for e in client.get(f"/accounts/{account_id}/timeline").json()]
    assert events[:2] == ["task.completed", "task.updated"]
    assert client.get(f"/accounts/{account_id}/audit").status_code == 403  # no audit.read
    client.send("POST", "/auth/logout")

    client.login("b@verkies.test")  # owns nothing: sees neither the account nor its task
    assert client.get(f"/accounts/{account_id}").status_code == 404
    assert client.get("/accounts").json() == []
    assert client.send("POST", f"/tasks/{task_id}/complete", json={}).status_code == 404
    assert client.get("/opportunities/requires-attention").json() == []
    client.send("POST", "/auth/logout")

    client.login("viewer@verkies.test")  # accounts.read: sees everything, decides nothing
    (listed,) = client.get("/accounts", params={"q": "harbour"}).json()
    assert listed["id"] == account_id and listed["owner"]["id"] == str(seller_a)
    assert client.get("/accounts", params={"q": "harbour.test"}).json()[0]["id"] == account_id
    assert client.get("/accounts", params={"q": "zzz"}).json() == []
    assert (
        client.send("POST", f"/prospects/{run_id}/reject", json={"reason": "wrong_icp"}).status_code
        == 403
    )
