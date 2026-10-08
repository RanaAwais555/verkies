"""CSV import end to end: upload, map, check every row, research the chosen ones, export."""

import csv
import io
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.main import create_app
from app.research.router import get_enqueuer
from tests.integration.conftest import ApiClient, make_user

pytestmark = pytest.mark.integration

CSV = """Company;Homepage;Sector;Country
Fresh Ltd;https://fresh.test;Legal;GB
Known Co;known.test;Retail;GB
Fresh again;www.fresh.test/about;Legal;GB
Broken;not a website;;
Spam Inc;spam.test;;
Harbour Immigration;harbour-new.test;Legal;GB
Old Run;old.test;;
No Site;;;
"""


@pytest.fixture
def queued() -> list[uuid.UUID]:
    return []


@pytest.fixture
def client(engine: Engine, queued: list[uuid.UUID]) -> Iterator[ApiClient]:
    app = create_app()
    app.dependency_overrides[get_enqueuer] = lambda: queued.append
    with TestClient(app) as http:
        yield ApiClient(http)


def _seed(engine: Engine, user_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        for name, domain in (
            ("Known Co", "known.test"),
            ("Harbour Immigration Ltd", "harbour.test"),
        ):
            account_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO accounts (id, name, primary_domain, account_type, created_at,"
                    " updated_at) VALUES (:id, :n, :d, 'prospect', now(), now())"
                ),
                {"id": account_id, "n": name, "d": domain},
            )
            conn.execute(
                text(
                    "INSERT INTO account_domains (id, account_id, domain, is_primary, created_at)"
                    " VALUES (gen_random_uuid(), :id, :d, true, now())"
                ),
                {"id": account_id, "d": domain},
            )
        conn.execute(
            text(
                "INSERT INTO suppressions (id, kind, value, reason, added_at)"
                " VALUES (gen_random_uuid(), 'domain', 'spam.test', 'asked us not to', now())"
            )
        )
        conn.execute(
            text(
                "INSERT INTO research_runs (id, input_url, normalised_domain, requested_by_id,"
                " status, review_status, retry_count, crawl_budget, possible_duplicate_of,"
                " created_at, updated_at) VALUES (gen_random_uuid(), 'https://old.test/',"
                " 'old.test', :u, 'completed', 'rejected', 0, '{}', '[]', now(), now())"
            ),
            {"u": user_id},
        )


def test_import_checks_every_row_and_researches_the_chosen_ones(
    client: ApiClient, engine: Engine, queued: list[uuid.UUID]
) -> None:
    user_id = make_user(engine, "r@verkies.test", ["sales_manager"])
    _seed(engine, user_id)
    client.login("r@verkies.test")

    uploaded = client.send(
        "POST", "/discovery/imports", json={"filename": "leads.csv", "content": CSV}
    )
    assert uploaded.status_code == 201, uploaded.text
    job = uploaded.json()
    assert job["status"] == "uploaded" and job["row_count"] == 8
    assert job["columns"] == ["Company", "Homepage", "Sector", "Country"]
    assert job["mapping"] == {
        "name": "Company",
        "website": "Homepage",
        "industry": "Sector",
        "country": "Country",
    }
    assert {r["status"] for r in job["rows"]} == {"pending"}

    early = client.send(
        "POST", f"/discovery/imports/{job['id']}/research", json={"row_ids": [job["rows"][0]["id"]]}
    )
    assert early.status_code == 409  # map and check first

    checked = client.send(
        "PUT", f"/discovery/imports/{job['id']}/mapping", json={"mapping": job["mapping"]}
    )
    assert checked.status_code == 200, checked.text
    detail = checked.json()
    by_row = {r["row_number"]: r for r in detail["rows"]}
    assert {n: r["status"] for n, r in by_row.items()} == {
        1: "new",
        2: "existing_account",
        3: "duplicate_in_file",
        4: "invalid",
        5: "suppressed",
        6: "possible_duplicate",
        7: "already_researched",
        8: "invalid",
    }
    assert by_row[1]["normalised_domain"] == "fresh.test" and by_row[1]["industry"] == "Legal"
    assert by_row[3]["status_detail"] == "Same website as row 1."
    assert by_row[2]["matched_account_id"] and by_row[6]["matched_account_id"]
    assert "Harbour Immigration Ltd" in by_row[6]["status_detail"]
    assert by_row[7]["research_run_id"] and "rejected" in by_row[7]["status_detail"]
    assert by_row[8]["status_detail"] == "No website in this row."
    assert detail["stats"] == {
        "new": 1,
        "existing_account": 1,
        "duplicate_in_file": 1,
        "invalid": 2,
        "suppressed": 1,
        "possible_duplicate": 1,
        "already_researched": 1,
    }

    started = client.send(
        "POST",
        f"/discovery/imports/{job['id']}/research",
        json={"row_ids": [by_row[n]["id"] for n in (1, 2, 5, 6)]},
    ).json()
    assert len(started["started"]) == 2 and started["queue_failures"] == 0
    assert queued == [uuid.UUID(i) for i in started["started"]]
    assert set(started["skipped"]) == {by_row[2]["id"], by_row[5]["id"]}
    assert "suppressed" in started["skipped"][by_row[5]["id"]]

    after = client.get(f"/discovery/imports/{job['id']}", params={"status": "queued"}).json()
    assert [r["row_number"] for r in after["rows"]] == [1, 6]
    assert all(
        r["run_status"] == "queued" and r["run_review_status"] == "pending" for r in after["rows"]
    )
    # Re-checking keeps researched rows, and the rest of the file sees them.
    rechecked = client.send(
        "PUT", f"/discovery/imports/{job['id']}/mapping", json={"mapping": job["mapping"]}
    ).json()
    assert {r["row_number"]: r["status"] for r in rechecked["rows"]}[1] == "queued"
    again = client.send(
        "POST", f"/discovery/imports/{job['id']}/research", json={"row_ids": [by_row[1]["id"]]}
    )
    assert again.json()["started"] == []

    history = client.get("/discovery/imports").json()
    assert [h["name"] for h in history] == ["leads.csv"] and history[0]["status"] == "checked"
    with engine.connect() as conn:
        actions = set(conn.execute(text("SELECT action FROM audit_log")).scalars())
    assert {"discovery.imported", "discovery.checked", "research.started"} <= actions


def test_imports_are_private_to_their_owner_and_need_research_rights(
    client: ApiClient, engine: Engine, make_api
) -> None:  # type: ignore[no-untyped-def]
    make_user(engine, "a@verkies.test", ["salesperson"])
    make_user(engine, "b@verkies.test", ["salesperson"])
    make_user(engine, "v@verkies.test", ["viewer"])
    client.login("a@verkies.test")
    job = client.send("POST", "/discovery/imports", json={"content": "Website\na.test\n"}).json()

    other = make_api()
    other.login("b@verkies.test")
    assert other.get(f"/discovery/imports/{job['id']}").status_code == 404
    assert other.get("/discovery/imports").json() == []
    viewer = make_api()
    viewer.login("v@verkies.test")
    assert viewer.get("/discovery/imports").status_code == 403
    bad = client.send("POST", "/discovery/imports", json={"content": "Website\n"})
    assert bad.status_code == 422 and "no data" in bad.json()["error"]["message"]


def test_export_is_spreadsheet_safe_scoped_and_audited(client: ApiClient, engine: Engine) -> None:
    make_user(engine, "m@verkies.test", ["sales_manager"])
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, name, primary_domain, account_type, created_at,"
                " updated_at) VALUES (gen_random_uuid(), '=HYPERLINK(\"x\")', 'evil.test',"
                " 'prospect', now(), now())"
            )
        )
    client.login("m@verkies.test")
    response = client.get("/accounts/export")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows[0]["name"] == '\'=HYPERLINK("x")' and rows[0]["primary_domain"] == "evil.test"
    data = json.loads(client.get("/accounts/export", params={"format": "json"}).text)
    assert data[0]["name"] == '=HYPERLINK("x")'  # JSON keeps the real value
    entries = client.get("/audit", params={"object_table": "accounts"}).json()["items"]
    assert [e["action"] for e in entries[:2]] == ["accounts.exported", "accounts.exported"]
