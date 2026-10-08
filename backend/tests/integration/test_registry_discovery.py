"""Companies House discovery end to end: the advanced search (fake register), the worker that
finds websites (fake web search, real fetcher against local sites) and the final checks."""

import asyncio
import json
import threading
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.discovery.router import get_companies_house, get_website_finder_enqueuer
from app.discovery.websites import find_websites
from app.main import create_app
from app.providers.fetch.netguard import parse_networks
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.fetch.types import FetchBudget
from app.providers.search import SearchResult
from app.providers.storage import LocalStorage
from app.registry.companies_house import CompaniesHouse
from app.research.source import CachedPageSource
from tests.integration.conftest import ApiClient, make_user
from tests.unit.test_netguard import FakeResolver

pytestmark = pytest.mark.integration

FOOTER = "<footer>Bright Legal Ltd. Registered in England and Wales No. 11111111.</footer>"
PAGES = {
    "brightlegal.test": f"<html><body><h1>Bright Legal</h1>{FOOTER}</body></html>",
    # Same name, different company number: must not be accepted.
    "bright-legal-other.test": "<html><body><h1>Bright Legal</h1>"
    "<footer>Company no. 99999999</footer></body></html>",
    "quietfirm.test": "<html><body><h1>Quiet Firm</h1><p>No number shown here.</p></body></html>",
}
SEARCH = {
    "items": [
        {
            "company_number": "11111111",
            "company_name": "BRIGHT LEGAL LTD",
            "company_status": "active",
            "registered_office_address": {"locality": "Leeds"},
            "sic_codes": ["69102"],
            "date_of_creation": "2018-05-01",
        },
        {
            "company_number": "22222222",
            "company_name": "QUIET FIRM LIMITED",
            "company_status": "active",
            "registered_office_address": {"locality": "Leeds"},
            "sic_codes": ["69102"],
        },
        {
            "company_number": "33333333",
            "company_name": "KNOWN LAW LTD",
            "company_status": "active",
            "registered_office_address": {"locality": "Leeds"},
            "sic_codes": ["69102"],
        },
    ]
}
requests: list[str] = []


@pytest.fixture
def port() -> Iterator[int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            host = (self.headers.get("Host") or "").split(":")[0]
            requests.append(f"{host}{self.path}")
            if host == "ch.test" and self.path.startswith("/advanced-search/companies?"):
                ctype, body = "application/json", json.dumps(SEARCH)
            elif host in PAGES and self.path == "/":
                ctype, body = "text/html", PAGES[host]
            else:
                self.send_response(404)
                self.end_headers()
                return
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


class FakeSearch:
    name = "fake"

    def __init__(self, port: int) -> None:
        self.port = port
        self.queries: list[str] = []

    async def search(
        self, query: str, *, pages: int = 1, language: str | None = None
    ) -> list[SearchResult]:
        self.queries.append(query)
        p = self.port
        if "Bright Legal" in query:
            return [
                SearchResult("Bright Legal | Leeds", f"http://bright-legal-other.test:{p}/", ""),
                SearchResult("Bright Legal Solicitors", f"http://brightlegal.test:{p}/", ""),
            ]
        return [SearchResult("Quiet Firm", f"http://quietfirm.test:{p}/", "")]


def test_registry_search_finds_only_websites_that_show_the_same_number(
    engine: Engine, port: int, tmp_path: Path
) -> None:
    settings = get_settings().model_copy(
        update={"crawl_allowed_ports": [port, 80, 443], "fetch_private_allowlist": ["127.0.0.0/8"]}
    )
    queued: list[uuid.UUID] = []
    app = create_app()
    app.dependency_overrides[get_companies_house] = lambda: CompaniesHouse(
        "test-key", base_url=f"http://ch.test:{port}"
    )
    app.dependency_overrides[get_website_finder_enqueuer] = lambda: queued.append
    # The endpoint's own fetcher must reach ch.test on localhost.
    import app.discovery.router as router_module

    original = router_module.build_fetcher
    router_module.build_fetcher = lambda _s: SafeHttpFetcher(  # type: ignore[assignment]
        user_agent="VROSBot/test",
        budget=FetchBudget(allowed_ports=frozenset([port])),
        resolver=FakeResolver({"ch.test": ["127.0.0.1"]}),
        allowlist=parse_networks(["127.0.0.0/8"]),
    )
    make_user(engine, "r@verkies.test", ["sales_manager"])
    with engine.begin() as conn:
        account_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO accounts (id, name, account_type, created_at, updated_at)"
                " VALUES (:id, 'Known Law', 'prospect', now(), now())"
            ),
            {"id": account_id},
        )
        conn.execute(
            text(
                "INSERT INTO account_identifiers (id, account_id, scheme, value, created_at)"
                " VALUES (gen_random_uuid(), :id, 'companies_house', '33333333', now())"
            ),
            {"id": account_id},
        )
    try:
        with TestClient(app) as http:
            client = ApiClient(http)
            client.login("r@verkies.test")
            bad = client.send("POST", "/discovery/registry-searches", json={"sic_codes": ["6910"]})
            assert bad.status_code == 422
            response = client.send(
                "POST",
                "/discovery/registry-searches",
                json={"sic_codes": ["69102"], "location": "Leeds", "size": 10},
            )
            assert response.status_code == 201, response.text
            job = response.json()
            assert job["kind"] == "registry" and job["status"] == "running"
            assert job["name"] == "SIC 69102 in Leeds"
            assert {r["status"] for r in job["rows"]} == {"finding_website"}
            assert queued == [uuid.UUID(job["id"])]
            sent = next(r for r in requests if r.startswith("ch.test/advanced-search"))
            assert (
                "company_status=active" in sent
                and "sic_codes=69102" in sent
                and "location=Leeds" in sent
            )

            # The worker, run directly with a fake web search and the real fetcher.
            search = FakeSearch(port)

            async def work() -> dict[str, int]:
                engine_async = create_async_engine(settings.database_url, poolclass=NullPool)
                fetcher = SafeHttpFetcher(
                    user_agent="VROSBot/test",
                    budget=FetchBudget(allowed_ports=frozenset([port])),
                    resolver=FakeResolver({h: ["127.0.0.1"] for h in PAGES}),
                    allowlist=parse_networks(["127.0.0.0/8"]),
                )
                maker = async_sessionmaker(engine_async, expire_on_commit=False)
                try:
                    return await find_websites(
                        uuid.UUID(job["id"]),
                        maker,
                        search,
                        CachedPageSource(
                            sessionmaker=maker,
                            storage=LocalStorage(str(tmp_path)),
                            fetcher=fetcher,
                            renderer=None,
                            cache_days=0,
                        ),
                    )
                finally:
                    await fetcher.aclose()
                    await engine_async.dispose()

            report = asyncio.run(work())
            assert report == {"rows": 3, "websites": 1}
            assert search.queries == [
                '"Bright Legal" Leeds',
                '"Quiet Firm" Leeds',
            ]  # known one skipped

            done = client.get(f"/discovery/imports/{job['id']}").json()
            assert done["status"] == "checked"
            rows = {r["raw"]["number"]: r for r in done["rows"]}
            bright = rows["11111111"]
            assert bright["status"] == "new" and bright["normalised_domain"] == "brightlegal.test"
            assert bright["raw"]["website_note"] == "The homepage shows company number 11111111."
            quiet = rows["22222222"]
            assert quiet["status"] == "no_website" and quiet["website_url"] is None
            assert "No website showing company number 22222222" in quiet["status_detail"]
            known = rows["33333333"]
            assert known["status"] == "existing_account" and known["matched_account_id"] == str(
                account_id
            )
    finally:
        router_module.build_fetcher = original


def test_registry_search_needs_a_key(engine: Engine) -> None:
    app = create_app()
    app.dependency_overrides[get_companies_house] = lambda: CompaniesHouse(None)
    make_user(engine, "r@verkies.test", ["researcher"])
    with TestClient(app) as http:
        client = ApiClient(http)
        client.login("r@verkies.test")
        response = client.send(
            "POST", "/discovery/registry-searches", json={"sic_codes": ["69102"]}
        )
        assert (
            response.status_code == 503
            and response.json()["error"]["code"] == "registry_unavailable"
        )
