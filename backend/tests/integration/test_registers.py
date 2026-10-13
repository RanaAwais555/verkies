"""Registers kept in VROS (slice 8.1): refreshing the SRA register from a fake SRA through the
real safe fetcher, the status and refresh routes, and searching the register into a checked
discovery job."""

import asyncio
import json
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import Settings, get_settings
from app.core.enums import RegisterRefreshStatus
from app.main import create_app
from app.providers.fetch.netguard import parse_networks
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.fetch.types import FetchBudget
from app.registers import refresh as refresh_module
from app.registers.refresh import RefreshResult, refresh_due, refresh_source
from app.registers.router import get_refresh_enqueuer
from app.registers.sra import SraRegister
from tests.integration.conftest import ApiClient, make_user
from tests.unit.test_netguard import FakeResolver
from tests.unit.test_registers import org

pytestmark = pytest.mark.integration

KEY = "test-sra-key"
served: dict[str, Any] = {"orgs": [], "calls": 0}


def london_firms() -> list[dict[str, object]]:
    return [
        org(
            1,
            "Alpha Immigration Ltd",
            CompanyRegNo="11111111",
            Websites=["www.alpha.test"],
            NoOfOffices=2,
        ),
        org(
            2,
            "Beta Law LLP",
            CompanyRegNo="OC222222",
            Websites=["www.beta.test"],
            WorkArea=["Immigration", "Family / Matrimonial", "Criminal", "Probate"],
        ),
        org(
            3,
            "Gamma Solicitors",
            Websites=["www.gamma.test"],
            WorkArea=["Property - Residential"],
            Offices=[{"Postcode": "M1 1AA", "Town": "Manchester", "OfficeType": "HO"}],
        ),
        org(4, "Delta Legal", WorkArea=["Immigration"]),  # no website
        org(5, "Old Firm", AuthorisationStatus="REVOKE", Websites=["www.old.test"]),
    ]


@pytest.fixture
def port() -> Iterator[int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            served["calls"] += 1
            if self.headers.get("Ocp-Apim-Subscription-Key") != KEY:
                self.send_response(401)
                self.end_headers()
                return
            data = json.dumps(
                {"Count": len(served["orgs"]), "Organisations": served["orgs"]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    served.update(orgs=london_firms(), calls=0)
    # Only the SRA, served by the fake (the dict is changed in place: the router holds it too).
    original = dict(refresh_module.SOURCES)
    refresh_module.SOURCES.clear()
    refresh_module.SOURCES["sra"] = SraRegister(f"http://sra.test:{server.server_address[1]}/all")
    yield server.server_address[1]
    refresh_module.SOURCES.clear()
    refresh_module.SOURCES.update(original)
    server.shutdown()


def settings_with(key: str | None) -> Settings:
    return get_settings().model_copy(update={"sra_api_key": SecretStr(key) if key else None})


def run_refresh(port: int, key: str | None = KEY, *, now: datetime | None = None) -> RefreshResult:
    settings = settings_with(key)

    async def go() -> RefreshResult:
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        fetcher = SafeHttpFetcher(
            user_agent="VROSBot/test",
            budget=FetchBudget(allowed_ports=frozenset([port])),
            resolver=FakeResolver({"sra.test": ["127.0.0.1"]}),
            allowlist=parse_networks(["127.0.0.0/8"]),
        )
        try:
            return await refresh_source(
                "sra",
                async_sessionmaker(engine, expire_on_commit=False),
                fetcher,
                settings,
                now=now,
            )
        finally:
            await fetcher.aclose()
            await engine.dispose()

    return asyncio.run(go())


def source_row(engine: Engine) -> dict[str, Any]:
    with engine.connect() as conn:
        return dict(
            conn.execute(text("SELECT * FROM register_sources WHERE key = 'sra'")).mappings().one()
        )


def records(engine: Engine) -> dict[str, dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM register_records WHERE source = 'sra'")).mappings()
        return {r["source_id"]: dict(r) for r in rows}


def test_a_refresh_applies_new_changed_and_removed_firms_and_skips_identical_downloads(
    engine: Engine, port: int
) -> None:
    first = run_refresh(port)
    assert (first.status, first.new, first.updated, first.removed) == (
        RegisterRefreshStatus.OK,
        5,
        0,
        0,
    )
    row = source_row(engine)
    assert (row["last_status"], row["record_count"], row["active_count"]) == ("ok", 5, 4)
    kept = records(engine)
    alpha = kept["1"]
    assert alpha["company_number"] == "11111111" and alpha["website"] == "https://www.alpha.test/"
    assert alpha["postcode_areas"] == ["SE"] and alpha["areas"] == ["Immigration"]
    assert kept["5"]["active"] is False

    assert run_refresh(port).status == RegisterRefreshStatus.UNCHANGED
    assert source_row(engine)["last_status"] == "unchanged"

    # The SRA drops Gamma, Beta moves office, and a new firm appears.
    firms = london_firms()
    firms[1]["Offices"] = [{"Postcode": "W1 1AA", "Town": "London", "OfficeType": "HO"}]
    served["orgs"] = [f for f in firms if f["SraNumber"] != 3] + [org(6, "Epsilon Law")]
    changed = run_refresh(port)
    assert (changed.new, changed.updated, changed.removed) == (1, 1, 1)
    kept = records(engine)
    assert kept["2"]["postcode_areas"] == ["W"]
    assert kept["3"]["removed_at"] is not None and kept["3"]["active"] is False
    assert kept["6"]["first_seen_at"] is not None
    assert source_row(engine)["detail"] == {"new": 1, "updated": 1, "removed": 1}

    # Gamma comes back: it is the same record again, not a new one.
    served["orgs"] = [*served["orgs"], org(3, "Gamma Solicitors")]
    back = run_refresh(port)
    assert (back.new, back.updated) == (0, 1)
    assert records(engine)["3"]["removed_at"] is None


def test_a_broken_or_short_download_leaves_the_copy_as_it_was(engine: Engine, port: int) -> None:
    run_refresh(port)
    served["orgs"] = served["orgs"][:1]  # 1 firm against 5 kept: not believable
    short = run_refresh(port)
    assert short.status == RegisterRefreshStatus.FAILED and "1 organisations" in (short.error or "")
    assert all(r["removed_at"] is None for r in records(engine).values())
    row = source_row(engine)
    assert row["last_status"] == "failed" and row["record_count"] == 5

    refused = run_refresh(port, key="wrong-key")
    assert refused.status == RegisterRefreshStatus.FAILED
    assert "refused" in (refused.error or "")
    assert len(records(engine)) == 5


def test_without_a_key_the_source_is_unconfigured_and_never_called(
    engine: Engine, port: int
) -> None:
    result = run_refresh(port, key=None)
    assert result.status == RegisterRefreshStatus.UNCONFIGURED
    assert served["calls"] == 0 and records(engine) == {}


def test_the_scheduled_run_refreshes_only_sources_that_are_due(engine: Engine, port: int) -> None:
    settings = settings_with(KEY)

    def due_run(now: datetime) -> dict[str, str]:
        async def go() -> dict[str, str]:
            engine_async = create_async_engine(settings.database_url, poolclass=NullPool)
            fetcher = SafeHttpFetcher(
                user_agent="VROSBot/test",
                budget=FetchBudget(allowed_ports=frozenset([port])),
                resolver=FakeResolver({"sra.test": ["127.0.0.1"]}),
                allowlist=parse_networks(["127.0.0.0/8"]),
            )
            try:
                return await refresh_due(
                    async_sessionmaker(engine_async, expire_on_commit=False),
                    fetcher,
                    settings,
                    now=now,
                )
            finally:
                await fetcher.aclose()
                await engine_async.dispose()

        return asyncio.run(go())

    start = datetime(2026, 10, 1, 3, 20, tzinfo=UTC)
    assert due_run(start) == {"sra": "ok"}
    assert due_run(start + timedelta(hours=1)) == {"sra": "not due"}
    assert due_run(start + timedelta(hours=23)) == {"sra": "unchanged"}


def test_admins_see_each_source_and_can_refresh_now(engine: Engine, port: int) -> None:
    run_refresh(port)
    queued: list[str] = []
    app = create_app()
    app.dependency_overrides[get_refresh_enqueuer] = lambda: queued.append
    make_user(engine, "admin@verkies.test", ["admin"])
    make_user(engine, "r@verkies.test", ["researcher"])
    with TestClient(app) as http:
        admin = ApiClient(http)
        admin.login("admin@verkies.test")
        [sra] = admin.get("/registers/sources").json()
        assert sra["key"] == "sra" and sra["last_status"] == "ok"
        assert (sra["record_count"], sra["active_count"], sra["cadence_hours"]) == (5, 4, 24)
        assert "Solicitors Regulation Authority" in sra["attribution"]
        assert admin.send("POST", "/registers/sources/sra/refresh").status_code == 202
        assert queued == ["sra"]
        assert admin.send("POST", "/registers/sources/nope/refresh").status_code == 404

    with TestClient(app) as http:
        researcher = ApiClient(http)
        researcher.login("r@verkies.test")
        assert researcher.get("/registers/sources").status_code == 200
        assert researcher.send("POST", "/registers/sources/sra/refresh").status_code == 403
        assert queued == ["sra"]


def test_searching_the_register_makes_a_checked_discovery_job(engine: Engine, port: int) -> None:
    make_user(engine, "r@verkies.test", ["researcher"])
    with TestClient(create_app()) as http:
        client = ApiClient(http)
        client.login("r@verkies.test")
        body = {"source": "sra", "areas": ["Immigration"], "postcode_areas": ["SE", "W"]}
        before = client.send("POST", "/discovery/register-searches", json=body)
        assert before.status_code == 409
        assert before.json()["error"]["code"] == "register_not_loaded"

        run_refresh(port)
        with engine.begin() as conn:
            account_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO accounts (id, name, account_type, created_at, updated_at)"
                    " VALUES (:id, 'Alpha', 'prospect', now(), now())"
                ),
                {"id": account_id},
            )
            conn.execute(
                text(
                    "INSERT INTO account_identifiers (id, account_id, scheme, value, created_at)"
                    " VALUES (gen_random_uuid(), :id, 'companies_house', '11111111', now())"
                ),
                {"id": account_id},
            )

        options = client.get("/registers/sra/options").json()
        assert options["loaded"] is True
        assert {a["area"]: a["organisations"] for a in options["areas"]}["Immigration"] == 3
        assert "SE" in options["london_postcode_areas"]

        response = client.send("POST", "/discovery/register-searches", json=body)
        assert response.status_code == 201, response.text
        job = response.json()
        assert job["kind"] == "register" and job["status"] == "checked"
        assert job["name"].startswith("SRA: Immigration; in SE, W")
        rows = {r["raw"]["register_id"]: r for r in job["rows"]}
        # Gamma (Manchester, property), Delta (no website) and Old Firm (revoked) are left out.
        assert set(rows) == {"1", "2"}
        assert rows["1"]["status"] == "existing_account"
        assert rows["1"]["matched_account_id"] == str(account_id)
        beta = rows["2"]
        assert beta["status"] == "new" and beta["normalised_domain"] == "beta.test"
        assert beta["raw"]["number"] == "OC222222"
        assert "SRA 2" in beta["notes"]

        specialists = client.send(
            "POST",
            "/discovery/register-searches",
            json={**body, "max_areas": 3, "offices_min": 2},
        ).json()
        assert [r["raw"]["register_id"] for r in specialists["rows"]] == ["1"]

        nothing = client.send(
            "POST",
            "/discovery/register-searches",
            json={"source": "sra", "areas": ["Immigration"], "postcode_areas": ["B"]},
        )
        assert nothing.status_code == 422
        unknown = client.send("POST", "/discovery/register-searches", json={"source": "nope"})
        assert unknown.status_code == 404


def test_each_register_offers_its_own_filters_and_charities_search_by_income(
    engine: Engine,
) -> None:
    """Charities (slice 8.3): categories, location and income from the register itself."""
    rows = [
        ("1100001", "Hope Trust", 512_000, ["E"], ["Education/training"], "https://hope.test/"),
        ("1100002", "Big Health", 25_000_000, ["SE"], ["Health"], "https://bighealth.test/"),
        ("1100003", "Small Help", 40_000, ["E"], ["Education/training"], "https://small.test/"),
        ("1100004", "Leeds Learn", 600_000, ["LS"], ["Education/training"], "https://ll.test/"),
    ]
    with engine.begin() as conn:
        for number, name, income, postcodes, areas, site in rows:
            conn.execute(
                text(
                    "INSERT INTO register_records (id, source, source_id, name, active, website,"
                    " postcode_areas, areas, income, first_seen_at, last_seen_at, data)"
                    " VALUES (gen_random_uuid(), 'charity', :n, :name, true, :site, :pc, :areas,"
                    " :income, now(), now(), '{}')"
                ),
                {
                    "n": number,
                    "name": name,
                    "site": site,
                    "pc": postcodes,
                    "areas": areas,
                    "income": income,
                },
            )
        conn.execute(
            text(
                "INSERT INTO register_sources (key, record_count, active_count, detail)"
                " VALUES ('charity', 4, 4, '{}')"
            )
        )
    make_user(engine, "r@verkies.test", ["researcher"])
    with TestClient(create_app()) as http:
        client = ApiClient(http)
        client.login("r@verkies.test")
        sources = {s["key"]: s for s in client.get("/registers/sources").json()}
        assert {"sra", "iaa", "gias", "charity"} <= set(sources)
        assert sources["charity"]["short_name"] == "Charities"

        options = client.get("/registers/charity/options").json()
        assert options["area_label"] == "What the charity does"
        assert (options["has_location"], options["has_income"], options["has_offices"]) == (
            True,
            True,
            False,
        )
        assert options["specialist_areas"] is None
        iaa = client.get("/registers/iaa/options").json()
        assert iaa["has_location"] is False and iaa["loaded"] is False

        job = client.send(
            "POST",
            "/discovery/register-searches",
            json={
                "source": "charity",
                "areas": ["Education/training"],
                "postcode_areas": ["E", "EC", "N", "NW", "SE", "SW", "W", "WC"],
                "income_min": 250_000,
                "income_max": 10_000_000,
            },
        )
        assert job.status_code == 201, job.text
        body = job.json()
        assert body["name"] == "Charities: Education/training; in London; income £250k-£10m"
        [hope] = body["rows"]
        assert hope["raw"]["register_id"] == "1100001" and hope["raw"]["income"] == "512000"
        assert "income £512,000" in hope["notes"]
