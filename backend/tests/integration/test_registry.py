"""Registry enrichment end to end: research reads the company number from the site, the
(fake) Companies House and Wikidata answer, and approval turns that into contacts and account
identifiers, so the same registered company under a second website joins the same account."""

import json
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.config import Settings, get_settings
from app.main import create_app
from app.registry.companies_house import CompaniesHouse
from app.registry.stage import Registries
from app.registry.wikidata import Wikidata
from app.research.router import get_enqueuer
from tests.fixtures.sites import (
    IMMIGRATION_ABOUT,
    IMMIGRATION_CONTACT,
    IMMIGRATION_HOME,
    IMMIGRATION_TEAM,
)
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_research import run_pipeline

pytestmark = pytest.mark.integration

HOME = IMMIGRATION_HOME.replace(
    "Established in 2009.</p>", "Established in 2009. Company number 06812345.</p>"
)
SITE = {
    "/": HOME,
    "/contact/": IMMIGRATION_CONTACT,
    "/our-team/": IMMIGRATION_TEAM,
    "/about-us/": IMMIGRATION_ABOUT,
}
COMPANY = {
    "company_number": "06812345",
    "company_name": "HARBOUR IMMIGRATION LTD",
    "company_status": "active",
    "date_of_creation": "2009-03-02",
    "sic_codes": ["69109"],
    "registered_office_address": {"locality": "London"},
}
OFFICERS = {
    "items": [
        {"name": "HART, Amelia Jane", "officer_role": "director", "appointed_on": "2009-03-02"},
        {"name": "SHAH, Priya", "officer_role": "director", "appointed_on": "2018-06-01"},
    ]
}
RECENT = (datetime.now(UTC) - timedelta(days=40)).date().isoformat()
FILINGS = {
    "items": [
        {
            "category": "accounts",
            "date": "2026-02-01",
            "description": "accounts-with-accounts-type-small",
            "description_values": {"made_up_date": "2025-06-30"},
        },
        {
            "category": "officers",
            "date": RECENT,
            "description": "appointment-of-director-with-name-date",
            "description_values": {"officer_name": "Priya Shah"},
        },
    ]
}
OWNERS = {
    "items": [
        {
            "kind": "individual-person-with-significant-control",
            "name_elements": {"forename": "Kemi", "surname": "Bello"},
            "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
        }
    ]
}
seen_auth: list[str] = []


@pytest.fixture
def port() -> Iterator[int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            host = (self.headers.get("Host") or "").split(":")[0]
            ctype, body = "text/html", None
            if host in ("harbour.test", "harbour-legal.test"):
                body = SITE.get(self.path)
            elif host == "ch.test":
                seen_auth.append(self.headers.get("Authorization") or "")
                ctype = "application/json"
                if self.path == "/company/06812345":
                    body = json.dumps(COMPANY)
                elif self.path.startswith("/company/06812345/officers"):
                    body = json.dumps(OFFICERS)
                elif self.path.startswith("/company/06812345/filing-history"):
                    body = json.dumps(FILINGS)
                elif self.path == "/company/06812345/persons-with-significant-control":
                    body = json.dumps(OWNERS)
            elif host == "wd.test":
                ctype, body = "application/sparql-results+json", '{"results": {"bindings": []}}'
            if body is None:
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


@pytest.fixture
def settings(port: int, tmp_path: Path) -> Settings:
    return get_settings().model_copy(
        update={
            "crawl_allowed_ports": [port, 80, 443],
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


def _research(client: ApiClient, settings: Settings, port: int, host: str) -> str:
    run = client.send("POST", "/research-runs", json={"url": f"http://{host}:{port}/"}).json()
    registries = Registries(
        CompaniesHouse("test-key", base_url=f"http://ch.test:{port}"),
        Wikidata(endpoint=f"http://wd.test:{port}/sparql"),
    )
    run_pipeline(
        uuid.UUID(run["id"]),
        settings,
        render=False,
        hosts=(host, "ch.test", "wd.test"),
        registries=registries,
    )
    return str(run["id"])


def test_registry_facts_become_contacts_and_identifiers(
    client: ApiClient, engine: Engine, settings: Settings, port: int
) -> None:
    make_user(engine, "m@verkies.test", ["sales_manager"])
    client.login("m@verkies.test")
    run_id = _research(client, settings, port, "harbour.test")

    detail = client.get(f"/research-runs/{run_id}").json()
    enrich = next(s for s in detail["stages"] if s["stage"] == "enrich")
    assert enrich["detail"]["companies_house"] == "06812345 (active)"
    assert enrich["detail"]["wikidata"] == "no item for this website"
    assert enrich["detail"]["officers"] == 2 and enrich["detail"]["errors"] == []
    assert enrich["detail"]["filing_events"] == 1 and enrich["detail"]["owners"] == 1
    assert seen_auth and all(a.startswith("Basic ") for a in seen_auth)

    registry = client.get(f"/research-runs/{run_id}/intelligence").json()["areas"]["registry"]
    assert {o["key"] for o in registry} == {
        "registry.companies_house",
        "registry.officer",
        "registry.accounts",
        "registry.owner",
    }
    assert all(o["evidence"]["evidence_type"] == "company_registry" for o in registry)
    sections = client.get(f"/research-runs/{run_id}/brief").json()["sections"]
    why_now = [c["text"] for c in sections["why_now"]["claims"]]
    assert f"Companies House, {RECENT}: Director appointed: Priya Shah." in why_now
    overview = sections["company_overview"]
    assert any(
        "Registered with Companies House as HARBOUR IMMIGRATION LTD (06812345)" in c["text"]
        for c in overview["claims"]
    )

    approval = client.send("POST", f"/prospects/{run_id}/approve", json={}).json()
    account = client.get(f"/accounts/{approval['account_id']}").json()
    contacts = {c["name"]: c for c in account["contacts"]}
    # Amelia is on the site and in the register: one contact. Priya is only registered;
    # Kemi owns the company (person with significant control).
    assert set(contacts) == {"Amelia Hart", "Daniel Okafor", "Priya Shah", "Kemi Bello"}
    assert contacts["Kemi Bello"]["title"] == "Owner (significant control)"
    assert account["company_size_band"] == "small"
    assert contacts["Priya Shah"]["source"] == "companies_house"
    assert contacts["Priya Shah"]["title"] == "Director"
    assert contacts["Priya Shah"]["decision_maker_role"] == "decision_maker"
    assert contacts["Priya Shah"]["email"] is None  # never invented
    with engine.connect() as conn:
        identifiers = conn.execute(
            text("SELECT scheme, value FROM account_identifiers WHERE account_id = :a"),
            {"a": approval["account_id"]},
        ).all()
    assert identifiers == [("companies_house", "06812345")]

    # A second website showing the same company number is the same legal entity.
    second = _research(client, settings, port, "harbour-legal.test")
    joined = client.send("POST", f"/prospects/{second}/approve", json={}).json()
    assert joined["account_id"] == approval["account_id"] and not joined["created_account"]
    domains = client.get(f"/accounts/{approval['account_id']}").json()["domains"]
    assert sorted(domains) == ["harbour-legal.test", "harbour.test"]
