"""Research runs end to end: API -> pipeline (real fetcher, DB, storage) -> progress API."""

import asyncio
import threading
import uuid
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import Settings, get_settings
from app.main import create_app
from app.providers.fetch.netguard import parse_networks
from app.providers.fetch.render import PlaywrightRenderer
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.fetch.types import FetchBudget
from app.providers.storage import LocalStorage
from app.registry.stage import Registries
from app.research.pipeline import PipelineDeps, run_research
from app.research.router import get_enqueuer
from app.signals.jobs import JobBoards
from tests.integration.conftest import ApiClient, make_user
from tests.unit.test_netguard import FakeResolver
from tests.unit.test_render import CHROMIUM, CHROMIUM_AVAILABLE

pytestmark = pytest.mark.integration

BODY = "<p>" + "Acme helps immigration firms manage cases and client documents. " * 15 + "</p>"
PAGES = {
    "/": f'<html><head><title>Acme</title></head><body><a href="/about">About</a>'
    f'<a href="/pricing">Pricing</a><a href="/private">Contact</a>{BODY}</body></html>',
    "/about": f"<html><head><title>About Acme</title></head><body>{BODY}</body></html>",
    "/pricing": '<html><head><title>Pricing</title><script src="/app.js" defer></script></head>'
    '<body><div id="root"></div></body></html>',
    "/app.js": "document.getElementById('root').innerHTML = '<h2>Plans from 99 GBP</h2>';",
    "/robots.txt": "User-agent: *\nDisallow: /private\n",
    "/sitemap.xml": "<urlset><url><loc>http://acme.test:{port}/team</loc></url></urlset>",
    "/team": f"<html><head><title>Team</title></head><body>{BODY}</body></html>",
}
TYPES = {
    "/app.js": "text/javascript",
    "/robots.txt": "text/plain",
    "/sitemap.xml": "application/xml",
}


@pytest.fixture
def acme() -> Iterator[tuple[int, list[str]]]:
    hits: list[str] = []
    port_box: list[int] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hits.append(self.path)
            if self.path not in PAGES:
                self.send_response(404)
                self.end_headers()
                return
            body = PAGES[self.path].replace("{port}", str(port_box[0])).encode()
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(self.path, "text/html; charset=utf-8"))
            self.send_header("Set-Cookie", "session=secret-from-acme")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port_box.append(server.server_address[1])
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield port_box[0], hits
    server.shutdown()


@pytest.fixture
def settings(acme: tuple[int, list[str]], tmp_path: Path) -> Settings:
    port, _ = acme
    return get_settings().model_copy(
        update={
            "crawl_allowed_ports": [port, 80, 443],
            "fetch_private_allowlist": ["127.0.0.0/8"],
            "crawl_min_interval_seconds": 0.0,
            "storage_dir": str(tmp_path / "storage"),
            "chromium_executable": CHROMIUM,
        }
    )


@pytest.fixture
def queued() -> list[uuid.UUID]:
    return []


@pytest.fixture
def research_api(
    engine: Engine, settings: Settings, queued: list[uuid.UUID]
) -> Iterator[ApiClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_enqueuer] = lambda: queued.append
    with TestClient(app) as http:
        yield ApiClient(http)


def run_pipeline(
    run_id: uuid.UUID,
    settings: Settings,
    *,
    render: bool = True,
    hosts: tuple[str, ...] = ("acme.test",),
    job_boards: JobBoards | None = None,
    registries: Registries | None = None,
) -> None:
    async def go() -> None:
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        fetcher = SafeHttpFetcher(
            user_agent=settings.crawler_user_agent,
            budget=FetchBudget(allowed_ports=frozenset(settings.crawl_allowed_ports)),
            resolver=FakeResolver({host: ["127.0.0.1"] for host in hosts}),
            allowlist=parse_networks(settings.fetch_private_allowlist),
        )
        renderer = (
            PlaywrightRenderer(fetcher, executable=CHROMIUM)
            if render and CHROMIUM_AVAILABLE
            else None
        )
        try:
            await run_research(
                run_id,
                PipelineDeps(
                    sessionmaker=async_sessionmaker(engine, expire_on_commit=False),
                    settings=settings,
                    fetcher=fetcher,
                    renderer=renderer,
                    storage=LocalStorage(settings.storage_dir),
                    job_boards=job_boards or JobBoards.default(),
                    # No network in tests: registries only when a test supplies fakes.
                    registries=registries or Registries.disabled(),
                ),
            )
        finally:
            await fetcher.aclose()
            await engine.dispose()

    asyncio.run(go())


def _start(api: ApiClient, url: str) -> dict:  # type: ignore[type-arg]
    response = api.send("POST", "/research-runs", json={"url": url})
    assert response.status_code == 202, response.text
    return response.json()


def test_research_run_crawls_and_reports_progress(
    research_api: ApiClient,
    engine: Engine,
    acme: tuple[int, list[str]],
    settings: Settings,
    queued: list[uuid.UUID],
) -> None:
    port, hits = acme
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    run = _start(research_api, f"http://acme.test:{port}")
    assert run["status"] == "queued" and run["normalised_domain"] == "acme.test"
    assert [s["stage"] for s in run["stages"]] == [
        "validate",
        "crawl",
        "extract",
        "signals",
        "enrich",
        "detect",
        "qualify",
        "score",
        "match",
        "brief",
    ]
    assert queued == [uuid.UUID(run["id"])]

    run_pipeline(uuid.UUID(run["id"]), settings)

    detail = research_api.get(f"/research-runs/{run['id']}").json()
    assert detail["status"] == "completed", detail
    assert detail["progress_pct"] == 100
    assert all(s["status"] == "completed" for s in detail["stages"])
    pages = {p["url"].split(str(port))[-1]: p for p in detail["pages"]}
    assert pages["/robots.txt"]["kind"] == "robots"
    assert pages["/"]["title"] == "Acme"
    assert pages["/about"]["category"] == "about"
    assert pages["/team"]["discovered_via"] == "sitemap"
    assert pages["/private"]["skip_reason"] == "robots_disallowed"
    assert "/private" not in hits  # robots.txt was obeyed
    if CHROMIUM_AVAILABLE:
        assert pages["/pricing"]["rendered"] is True
    crawl = next(s for s in detail["stages"] if s["stage"] == "crawl")
    assert crawl["detail"]["robots"] == "parsed"
    assert crawl["detail"]["pages_fetched"] >= 4

    with engine.connect() as conn:
        headers = conn.execute(text("SELECT headers FROM raw_responses")).scalars().all()
        rendered_html = (
            conn.execute(text("SELECT body_ref FROM raw_responses WHERE rendered")).scalars().all()
        )
    assert headers and all("set-cookie" not in h for h in headers)  # never store site cookies
    if CHROMIUM_AVAILABLE:
        body = LocalStorage(settings.storage_dir).get(rendered_html[0]).decode()
        assert "Plans from 99 GBP" in body


def test_retry_reuses_the_cache(
    research_api: ApiClient,
    engine: Engine,
    acme: tuple[int, list[str]],
    settings: Settings,
) -> None:
    port, hits = acme
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    run = _start(research_api, f"http://acme.test:{port}/")
    run_pipeline(uuid.UUID(run["id"]), settings, render=False)
    first_hits = len(hits)
    with engine.begin() as conn:
        conn.execute(text("UPDATE research_runs SET status = 'failed'"))
    assert research_api.send("POST", f"/research-runs/{run['id']}/retry").status_code == 202
    run_pipeline(uuid.UUID(run["id"]), settings, render=False)
    detail = research_api.get(f"/research-runs/{run['id']}").json()
    assert detail["status"] == "completed" and detail["retry_count"] == 1
    fetched = [p for p in detail["pages"] if p["kind"] == "page" and p["skip_reason"] is None]
    assert fetched and all(p["from_cache"] for p in fetched)
    assert len(hits) - first_hits <= 2  # only non-200 responses (e.g. sitemap misses) refetched


def test_cloud_metadata_url_fails_validation(
    research_api: ApiClient, engine: Engine, settings: Settings
) -> None:
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    run = _start(research_api, "http://169.254.169.254/latest/meta-data/")
    run_pipeline(uuid.UUID(run["id"]), settings, render=False)
    detail = research_api.get(f"/research-runs/{run['id']}").json()
    assert detail["status"] == "failed"
    assert "private, local or reserved" in detail["error"]
    validate = detail["stages"][0]
    assert validate["status"] == "failed" and detail["pages"] == []


def test_cancelled_run_is_not_started(
    research_api: ApiClient, engine: Engine, acme: tuple[int, list[str]], settings: Settings
) -> None:
    port, hits = acme
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    run = _start(research_api, f"http://acme.test:{port}")
    cancelled = research_api.send("POST", f"/research-runs/{run['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    run_pipeline(uuid.UUID(run["id"]), settings)
    assert hits == []
    again = research_api.send("POST", f"/research-runs/{run['id']}/cancel")
    assert again.status_code == 409


def test_one_active_run_per_domain(
    research_api: ApiClient, engine: Engine, acme: tuple[int, list[str]]
) -> None:
    port, _ = acme
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    _start(research_api, f"http://acme.test:{port}")
    duplicate = research_api.send(
        "POST", "/research-runs", json={"url": f"http://www.acme.test:{port}"}
    )
    assert duplicate.status_code == 409


@pytest.mark.parametrize(
    "url", ["", "notadomain", "ftp://acme.test/", "https://user:pw@acme.test/", "acme.test:2222"]
)
def test_bad_urls_are_rejected_up_front(research_api: ApiClient, engine: Engine, url: str) -> None:
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    response = research_api.send("POST", "/research-runs", json={"url": url})
    assert response.status_code == 422, response.text


def test_permissions_and_visibility(
    research_api: ApiClient,
    make_api: Callable[[], ApiClient],
    engine: Engine,
    acme: tuple[int, list[str]],
    settings: Settings,
    queued: list[uuid.UUID],
) -> None:
    port, _ = acme
    make_user(engine, "viewer@verkies.test", ["viewer"])
    make_user(engine, "sam@verkies.test", ["salesperson"])
    make_user(engine, "kim@verkies.test", ["salesperson"])
    research_api.login("viewer@verkies.test")
    denied = research_api.send("POST", "/research-runs", json={"url": f"http://acme.test:{port}"})
    assert denied.status_code == 403

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_enqueuer] = lambda: queued.append
    with TestClient(app) as sam_http, TestClient(app) as kim_http:
        sam, kim = ApiClient(sam_http), ApiClient(kim_http)
        sam.login("sam@verkies.test")
        kim.login("kim@verkies.test")
        run = _start(sam, f"http://acme.test:{port}")
        assert [r["id"] for r in sam.get("/research-runs").json()] == [run["id"]]
        # Salespeople review prospects, so they see every run, but only change their own.
        assert [r["id"] for r in kim.get("/research-runs").json()] == [run["id"]]
        assert kim.get(f"/research-runs/{run['id']}").status_code == 200
        assert kim.send("POST", f"/research-runs/{run['id']}/cancel").status_code == 403
        assert kim.send("POST", f"/research-runs/{run['id']}/retry").status_code == 403
    assert [r["id"] for r in research_api.get("/research-runs").json()] == [
        run["id"]
    ]  # viewer: all


def test_queue_outage_fails_the_run_cleanly(
    engine: Engine, settings: Settings, acme: tuple[int, list[str]]
) -> None:
    port, _ = acme

    def broken(_: uuid.UUID) -> None:
        raise ConnectionError("redis down")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_enqueuer] = lambda: broken
    make_user(engine, "r@verkies.test", ["researcher"])
    with TestClient(app) as http:
        api = ApiClient(http)
        api.login("r@verkies.test")
        response = api.send("POST", "/research-runs", json={"url": f"http://acme.test:{port}"})
        assert response.status_code == 503
        runs = api.get("/research-runs").json()
    assert runs[0]["status"] == "failed" and "queue" in runs[0]["error"]


def test_extract_stage_produces_evidence_backed_intelligence(
    research_api: ApiClient, engine: Engine, acme: tuple[int, list[str]], settings: Settings
) -> None:
    port, _ = acme
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    run = _start(research_api, f"http://acme.test:{port}/")
    run_pipeline(uuid.UUID(run["id"]), settings, render=False)

    detail = research_api.get(f"/research-runs/{run['id']}").json()
    extract = next(s for s in detail["stages"] if s["stage"] == "extract")
    assert extract["status"] == "completed", extract
    assert extract["detail"]["failed_extractors"] == []
    assert extract["detail"]["pages_analysed"] >= 3

    intel = research_api.get(f"/research-runs/{run['id']}/intelligence").json()
    assert intel["attempt"] == 0
    flat = {o["key"]: o for area in intel["areas"].values() for o in area}
    https = flat["website.https"]
    assert https["value"] is False  # the fixture site is plain http
    assert https["evidence"]["source_url"] == f"http://acme.test:{port}/"
    assert flat["seo.home_title"]["value"]["text"] == "Acme"
    assert flat["conversion.contact_form"]["value"] is False
    assert all(o["evidence"]["excerpt"] for o in flat.values())

    with engine.connect() as conn:
        orphaned = conn.execute(
            text(
                "SELECT count(*) FROM observations o LEFT JOIN evidence e ON e.id = o.evidence_id"
                " WHERE e.id IS NULL"
            )
        ).scalar_one()
    assert orphaned == 0


def test_observations_are_append_only_and_retry_shows_latest_attempt(
    research_api: ApiClient, engine: Engine, acme: tuple[int, list[str]], settings: Settings
) -> None:
    from sqlalchemy.exc import DBAPIError

    port, _ = acme
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    run = _start(research_api, f"http://acme.test:{port}/")
    run_pipeline(uuid.UUID(run["id"]), settings, render=False)
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text("UPDATE observations SET value = 'true'::jsonb"))

    first = research_api.get(f"/research-runs/{run['id']}/intelligence").json()
    with engine.begin() as conn:
        conn.execute(text("UPDATE research_runs SET status = 'failed'"))
    research_api.send("POST", f"/research-runs/{run['id']}/retry")
    run_pipeline(uuid.UUID(run["id"]), settings, render=False)
    second = research_api.get(f"/research-runs/{run['id']}/intelligence").json()
    assert second["attempt"] == 1
    count = lambda intel: sum(len(v) for v in intel["areas"].values())  # noqa: E731
    assert count(second) == count(first)  # history kept, but only the latest attempt shown
    with engine.connect() as conn:
        attempts = conn.execute(text("SELECT DISTINCT attempt FROM observations")).scalars().all()
    assert sorted(attempts) == [0, 1]


def test_assessment_ties_opportunities_scores_and_config_together(
    research_api: ApiClient,
    make_api: Callable[[], ApiClient],
    engine: Engine,
    acme: tuple[int, list[str]],
    settings: Settings,
) -> None:
    port, _ = acme
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    run = _start(research_api, f"http://acme.test:{port}/")
    run_pipeline(uuid.UUID(run["id"]), settings, render=False)

    detail = research_api.get(f"/research-runs/{run['id']}").json()
    assert detail["status"] == "completed", detail
    assert [s["status"] for s in detail["stages"]] == ["completed"] * 10

    a = research_api.get(f"/research-runs/{run['id']}/assessment").json()
    assert a["opportunities"], a
    for opportunity in a["opportunities"]:
        assert opportunity["evidence"], opportunity  # every opportunity cites evidence
        assert all(
            e["source_url"].startswith(f"http://acme.test:{port}") for e in opportunity["evidence"]
        )
    assert a["qualification"]["explanation"].startswith("ICP fit")
    score = a["score"]
    assert set(score["scores"]) == {
        "icp_score",
        "opportunity_score",
        "intent_score",
        "buyer_confidence",
        "data_confidence",
        "service_fit",
        "timing_score",
        "commercial_potential",
        "client_similarity",
        "evidence_strength",
    }
    assert score["scores"]["client_similarity"] is None
    assert score["priority_band"] in ("hot", "high", "qualified", "monitor", "reject")

    with engine.connect() as conn:
        versions = (
            conn.execute(
                text(
                    "SELECT c.version FROM score_snapshots s JOIN scoring_configs c"
                    " ON c.id = s.scoring_config_id"
                )
            )
            .scalars()
            .all()
        )
    assert versions == [1]


def test_config_versioning_changes_the_next_score(
    research_api: ApiClient,
    make_api: Callable[[], ApiClient],
    engine: Engine,
    acme: tuple[int, list[str]],
    settings: Settings,
) -> None:
    port, _ = acme
    make_user(engine, "admin@verkies.test", ["admin"])
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    current = research_api.get("/config/scoring").json()
    assert current["version"] == 1 and current["is_active"]
    assert (
        research_api.send("PUT", "/config/scoring", json={"config": current["config"]}).status_code
        == 403
    )

    admin = make_api()
    admin.login("admin@verkies.test")
    bad = dict(current["config"], weights=current["config"]["weights"] | {"icp_score": 0.9})
    rejected = admin.send("PUT", "/config/scoring", json={"config": bad})
    assert rejected.status_code == 422 and "sum to 1" in rejected.json()["error"]["message"]

    run = _start(research_api, f"http://acme.test:{port}/")
    run_pipeline(uuid.UUID(run["id"]), settings, render=False)
    before = research_api.get(f"/research-runs/{run['id']}/assessment").json()["score"]

    weights = current["config"]["weights"] | {"icp_score": 0.0, "intent_score": 0.32}
    updated = admin.send(
        "PUT",
        "/config/scoring",
        json={"config": dict(current["config"], weights=weights), "note": "Weight intent higher"},
    )
    assert updated.status_code == 200 and updated.json()["version"] == 2
    versions = admin.get("/config/scoring/versions").json()
    assert [(v["version"], v["is_active"]) for v in versions] == [(2, True), (1, False)]

    with engine.begin() as conn:
        conn.execute(text("UPDATE research_runs SET status = 'failed'"))
    research_api.send("POST", f"/research-runs/{run['id']}/retry")
    run_pipeline(uuid.UUID(run["id"]), settings, render=False)
    after = research_api.get(f"/research-runs/{run['id']}/assessment").json()["score"]
    assert after["breakdown"]["dimensions"]["icp_score"]["weight"] == 0.0
    assert before["breakdown"]["dimensions"]["icp_score"]["weight"] == 0.2
    with engine.connect() as conn:
        audit = conn.execute(
            text("SELECT action, reason FROM audit_log WHERE action LIKE 'config.%'")
        ).all()
    assert audit == [("config.scoring.updated", "Weight intent higher")]


def test_scoring_stops_cleanly_without_an_active_config(
    research_api: ApiClient, engine: Engine, acme: tuple[int, list[str]], settings: Settings
) -> None:
    port, _ = acme
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    with engine.begin() as conn:
        conn.execute(text("UPDATE icp_configs SET is_active = false"))
    try:
        run = _start(research_api, f"http://acme.test:{port}/")
        run_pipeline(uuid.UUID(run["id"]), settings, render=False)
        detail = research_api.get(f"/research-runs/{run['id']}").json()
        assert detail["status"] == "failed"
        assert "No active ICP or scoring configuration" in detail["error"]
        failed = [s["stage"] for s in detail["stages"] if s["status"] == "failed"]
        assert failed == ["detect"]
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE icp_configs SET is_active = true WHERE version = 1"))


def test_brief_is_stored_with_grounded_claims(
    research_api: ApiClient, engine: Engine, acme: tuple[int, list[str]], settings: Settings
) -> None:
    port, _ = acme
    make_user(engine, "r@verkies.test", ["researcher"])
    research_api.login("r@verkies.test")
    run = _start(research_api, f"http://acme.test:{port}/")
    run_pipeline(uuid.UUID(run["id"]), settings, render=False)

    brief = research_api.get(f"/research-runs/{run['id']}/brief").json()
    assert brief["mode"] == "template" and brief["generated_by"]["dropped"] == []
    assert brief["summary"]["domain"] == "acme.test"
    assert set(brief["sections"]) >= {
        "company_overview",
        "problem_detected",
        "why_verkies",
        "why_now",
        "recommended_service",
        "best_buyer",
        "similar_project",
        "sales_angle",
        "risks",
        "next_action",
    }
    claims = [c for s in brief["sections"].values() for c in s["claims"]]
    assert claims
    for claim in claims:
        if claim["claim_class"] in ("fact", "inference"):
            assert claim["evidence"], claim
            assert all(
                e["source_url"].startswith(f"http://acme.test:{port}") for e in claim["evidence"]
            )
    assert "Unknown" in (brief["sections"]["similar_project"]["unknown"] or "")

    with engine.connect() as conn:
        unsupported = conn.execute(
            text(
                "SELECT count(*) FROM claims c WHERE c.claim_class IN ('fact', 'inference')"
                " AND NOT EXISTS (SELECT 1 FROM claim_evidence ce WHERE ce.claim_id = c.id)"
            )
        ).scalar_one()
        recs_without_support = conn.execute(
            text(
                "SELECT count(*) FROM claims c WHERE c.claim_class = 'recommendation'"
                " AND NOT EXISTS (SELECT 1 FROM claim_support s WHERE s.claim_id = c.id)"
            )
        ).scalar_one()
        matches = conn.execute(text("SELECT count(*) FROM service_matches")).scalar_one()
        similarity = conn.execute(
            text("SELECT count(*), count(similarity_score) FROM similarity_results")
        ).one()
    assert unsupported == 0 and recs_without_support == 0
    assert matches <= 3
    assert similarity == (6, 0)  # six reference projects, all Unknown until profiles are complete
