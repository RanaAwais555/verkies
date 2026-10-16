"""/dashboard: exact counts for the Home charts, within the last 14 days, and only over what
each person may see."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.main import create_app
from tests.integration.conftest import ApiClient, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def client(engine: Engine) -> Iterator[ApiClient]:
    with TestClient(create_app()) as http:
        yield ApiClient(http)


def add_run(engine: Engine, user: uuid.UUID, days_ago: int, status: str, review: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO research_runs (id, input_url, normalised_domain, requested_by_id,"
                " status, review_status, retry_count, crawl_budget, possible_duplicate_of,"
                " created_at, updated_at) VALUES (gen_random_uuid(), 'https://a.test/', 'a.test',"
                " :u, :s, :r, 0, '{}', '[]', now() - make_interval(days => :d), now())"
            ),
            {"u": user, "s": status, "r": review, "d": days_ago},
        )


def add_account(engine: Engine, owner: uuid.UUID | None, band: str | None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, name, account_type, owner_id, priority_band,"
                " created_at, updated_at) VALUES (gen_random_uuid(), 'Co', 'prospect', :o, :b,"
                " now(), now())"
            ),
            {"o": owner, "b": band},
        )


def test_counts_runs_decisions_and_bands_within_what_each_person_sees(
    engine: Engine, client: ApiClient
) -> None:
    manager = make_user(engine, "m@verkies.test", ["sales_manager"])
    seller = make_user(engine, "s@verkies.test", ["salesperson"])
    nobody = make_user(engine, "n@verkies.test", [])
    add_run(engine, manager, 0, "completed", "approved")
    add_run(engine, manager, 0, "running", "pending")
    add_run(engine, seller, 3, "completed", "rejected")
    add_run(engine, nobody, 13, "completed", "pending")
    add_run(engine, manager, 20, "completed", "approved")  # outside the 14 days
    add_account(engine, manager, "hot")
    add_account(engine, seller, "high")
    add_account(engine, None, None)

    client.login("m@verkies.test")
    data = client.get("/dashboard").json()
    assert len(data["days"]) == 14
    assert [d["runs"] for d in data["days"]][-1] == 2  # today
    assert data["days"][-4]["runs"] == 1 and data["days"][0]["runs"] == 1
    assert sum(d["runs"] for d in data["days"]) == 4
    # Every completed run, whatever its age; a running one has no decision yet.
    assert data["decisions"] == {"pending": 1, "approved": 2, "rejected": 1}
    assert data["bands"] == {
        "hot": 1,
        "high": 1,
        "qualified": 0,
        "monitor": 0,
        "reject": 0,
        "unknown": 1,
    }

    # A salesperson sees their own and unassigned accounts, not the manager's.
    client.login("s@verkies.test")
    assert client.get("/dashboard").json()["bands"]["hot"] == 0

    # No role: only their own runs, and no accounts at all.
    client.login("n@verkies.test")
    data = client.get("/dashboard").json()
    assert sum(d["runs"] for d in data["days"]) == 1
    assert data["decisions"] == {"pending": 1, "approved": 0, "rejected": 0}
    assert sum(data["bands"].values()) == 0


def test_needs_sign_in(client: ApiClient) -> None:
    assert client.get("/dashboard").status_code == 401
