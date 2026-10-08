"""Signals end to end: a site that links to its job board and news feed, a fake board API, and
the run's intent, timing and "Why now" built from what they returned."""

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
from app.research.router import get_enqueuer
from app.signals.jobs import JobBoards
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_research import run_pipeline

pytestmark = pytest.mark.integration

RECENT = (datetime.now(UTC) - timedelta(days=12)).date().isoformat()
OLD = (datetime.now(UTC) - timedelta(days=500)).date().isoformat()
FILLER = "Shiplane is a cloud platform for dispatch, fleet tracking and proof of delivery. " * 8
HOME = f"""<html><head><title>Shiplane</title>
<link rel="alternate" type="application/rss+xml" title="News" href="/feed.xml"></head><body>
<h1>Logistics software</h1><p>{FILLER}</p><a href="/careers">Careers</a></body></html>"""
CAREERS = f"""<html><head><title>Careers</title></head><body><h1>Join us</h1><p>{FILLER}</p>
<a href="https://boards.greenhouse.io/shiplane">See open roles</a></body></html>"""
FEED = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>News</title>
<item><title>Shiplane raises seed round</title><link>http://shiplane.test/news/seed</link>
<pubDate>{datetime.fromisoformat(RECENT).strftime("%a, %d %b %Y 09:00:00 +0000")}</pubDate></item>
<item><title>Shiplane launches v1</title>
<pubDate>{datetime.fromisoformat(OLD).strftime("%a, %d %b %Y 09:00:00 +0000")}</pubDate></item>
</channel></rss>"""
BOARD = json.dumps(
    {
        "jobs": [
            {
                "title": "Senior Backend Engineer",
                "absolute_url": "https://boards.greenhouse.io/shiplane/jobs/1",
                "location": {"name": "London"},
                "first_published": f"{RECENT}T09:00:00Z",
            }
        ]
    }
)
ROUTES = {
    ("shiplane.test", "/"): ("text/html", HOME),
    ("shiplane.test", "/careers"): ("text/html", CAREERS),
    ("shiplane.test", "/feed.xml"): ("application/rss+xml", FEED),
    ("boards.test", "/v1/boards/shiplane/jobs"): ("application/json", BOARD),
}


@pytest.fixture
def port() -> Iterator[int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            host = (self.headers.get("Host") or "").split(":")[0]
            found = ROUTES.get((host, self.path))
            if found is None:
                self.send_response(404)
                self.end_headers()
                return
            ctype, body = found
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


def test_signals_from_the_linked_board_and_feed_drive_intent_timing_and_why_now(
    client: ApiClient, engine: Engine, settings: Settings, port: int
) -> None:
    make_user(engine, "r@verkies.test", ["sales_manager"])
    client.login("r@verkies.test")
    run = client.send(
        "POST", "/research-runs", json={"url": f"http://shiplane.test:{port}/"}
    ).json()
    boards = JobBoards({"greenhouse": f"http://boards.test:{port}/v1/boards/{{token}}/jobs"})
    run_pipeline(
        uuid.UUID(run["id"]),
        settings,
        render=False,
        hosts=("shiplane.test", "boards.test"),
        job_boards=boards,
    )

    detail = client.get(f"/research-runs/{run['id']}").json()
    assert detail["status"] == "completed", detail
    stages = {s["stage"]: s for s in detail["stages"]}
    assert list(stages)[:5] == ["validate", "crawl", "extract", "signals", "enrich"]
    report = stages["signals"]["detail"]
    assert report["job_boards"] == ["greenhouse"] and report["job_postings"] == 1
    assert report["news"] == 1 and report["errors"] == []  # the 500-day-old item is ignored

    signals = client.get(f"/research-runs/{run['id']}/intelligence").json()["areas"]["signals"]
    by_key = {o["key"]: o for o in signals}
    posting = by_key["signal.job_posting"]
    assert posting["value"]["signal"] == "developer_hiring"
    assert posting["evidence"]["evidence_type"] == "job_posting"
    assert posting["evidence"]["excerpt"].endswith(f"posted {RECENT} on Greenhouse")
    assert by_key["signal.news"]["value"] == {
        "signal": "funding",
        "title": "Shiplane raises seed round",
        "url": "http://shiplane.test/news/seed",
        "published": RECENT,
    }
    with engine.connect() as conn:
        published = conn.execute(
            text(
                "SELECT count(*) FROM evidence"
                " WHERE published_at IS NOT NULL AND research_run_id = :r"
            ),
            {"r": run["id"]},
        ).scalar_one()
    assert published == 2

    scores = client.get(f"/research-runs/{run['id']}/assessment").json()["score"]["scores"]
    assert scores["intent_score"] == 90  # hiring developers + funding, both very strong
    assert scores["timing_score"] == 90  # newest signal is 12 days old

    why_now = client.get(f"/research-runs/{run['id']}/brief").json()["sections"]["why_now"]
    texts = [c["text"] for c in why_now["claims"]]
    assert f"Hiring now on Greenhouse: Senior Backend Engineer (latest posted {RECENT})." in texts
    assert f"{RECENT}: Shiplane raises seed round." in texts
    assert all(c["evidence"] for c in why_now["claims"])
