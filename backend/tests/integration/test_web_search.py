"""Web search discovery through the API with a fake search provider (no network)."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.discovery.router import get_search_provider
from app.main import create_app
from app.providers.errors import ProviderUnavailable
from app.providers.search import SearchResult
from app.research.router import get_enqueuer
from tests.integration.conftest import ApiClient, make_user

pytestmark = pytest.mark.integration


class FakeSearch:
    name = "fake"

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results
        self.queries: list[tuple[str, int, str | None]] = []

    async def search(
        self, query: str, *, pages: int = 1, language: str | None = None
    ) -> list[SearchResult]:
        self.queries.append((query, pages, language))
        if self.results is None:
            raise ProviderUnavailable("Web search is not set up.")
        return self.results


RESULTS = [
    SearchResult(
        "Fresh Bakery | Leeds", "https://freshbakery.test/about", "Artisan bread in Leeds"
    ),
    SearchResult("Known Co - Home", "https://known.test/", "Already a client"),
    SearchResult("Fresh Bakery on LinkedIn", "https://www.linkedin.com/company/fresh", ""),
    SearchResult("Spam Bakery", "https://spam.test/", ""),
]


@pytest.fixture
def search() -> FakeSearch:
    return FakeSearch(RESULTS)


@pytest.fixture
def client(engine: Engine, search: FakeSearch) -> Iterator[ApiClient]:
    app = create_app()
    app.dependency_overrides[get_search_provider] = lambda: search
    app.dependency_overrides[get_enqueuer] = lambda: lambda _run_id: None
    with TestClient(app) as http:
        yield ApiClient(http)


def test_search_results_become_a_checked_discovery_job(
    client: ApiClient, engine: Engine, search: FakeSearch
) -> None:
    make_user(engine, "r@verkies.test", ["sales_manager"])
    with engine.begin() as conn:
        account_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO accounts (id, name, primary_domain, account_type, created_at,"
                " updated_at) VALUES (:id, 'Known Co', 'known.test', 'prospect', now(), now())"
            ),
            {"id": account_id},
        )
        conn.execute(
            text(
                "INSERT INTO account_domains (id, account_id, domain, is_primary, created_at)"
                " VALUES (gen_random_uuid(), :id, 'known.test', true, now())"
            ),
            {"id": account_id},
        )
        conn.execute(
            text(
                "INSERT INTO suppressions (id, kind, value, reason, added_at)"
                " VALUES (gen_random_uuid(), 'domain', 'spam.test', 'no', now())"
            )
        )
    client.login("r@verkies.test")

    response = client.send(
        "POST", "/discovery/searches", json={"query": "bakeries in Leeds", "pages": 2}
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert search.queries == [("bakeries in Leeds", 2, "en-GB")]
    assert (
        job["kind"] == "search"
        and job["status"] == "checked"
        and job["name"] == "bakeries in Leeds"
    )
    rows = {r["normalised_domain"]: r for r in job["rows"]}
    assert set(rows) == {"freshbakery.test", "known.test", "spam.test"}  # LinkedIn left out
    assert rows["freshbakery.test"]["status"] == "new"
    assert rows["freshbakery.test"]["name"] == "Fresh Bakery"
    assert rows["freshbakery.test"]["notes"] == "Artisan bread in Leeds"
    assert rows["known.test"]["status"] == "existing_account"
    assert rows["spam.test"]["status"] == "suppressed"

    started = client.send(
        "POST",
        f"/discovery/imports/{job['id']}/research",
        json={"row_ids": [rows["freshbakery.test"]["id"]]},
    ).json()
    assert len(started["started"]) == 1
    with engine.connect() as conn:
        action = conn.execute(
            text("SELECT new_value FROM audit_log WHERE action = 'discovery.searched'")
        ).scalar_one()
    assert action == {"query": "bakeries in Leeds", "results": 3}


def test_search_needs_a_provider_and_sensible_input(
    client: ApiClient, engine: Engine, search: FakeSearch
) -> None:
    make_user(engine, "r@verkies.test", ["researcher"])
    make_user(engine, "v@verkies.test", ["viewer"])
    client.login("v@verkies.test")
    assert client.send("POST", "/discovery/searches", json={"query": "bakeries"}).status_code == 403
    client.login("r@verkies.test")
    for body in (
        {"query": "ab"},
        {"query": "bakeries", "pages": 9},
        {"query": "bakeries", "language": "english"},
    ):
        assert client.send("POST", "/discovery/searches", json=body).status_code == 422
    search.results = []
    empty = client.send("POST", "/discovery/searches", json={"query": "nothing here"})
    assert empty.status_code == 422 and "no company websites" in empty.json()["error"]["message"]
    search.results = None
    down = client.send("POST", "/discovery/searches", json={"query": "bakeries"})
    assert down.status_code == 503 and down.json()["error"]["code"] == "search_unavailable"
