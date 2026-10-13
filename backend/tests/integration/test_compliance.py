"""Website compliance end to end (slice 8.2): research on a law firm's site (local) with a fake
Wayback Machine finds what the SRA asks for and is missing, how long the homepage has gone
unchanged, and raises "Website compliance fixes" with that evidence."""

import json
import threading
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings, get_settings
from app.main import create_app
from app.research.router import get_enqueuer
from app.sitecheck.stage import SiteChecks
from app.sitecheck.wayback import Wayback
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_research import run_pipeline

pytestmark = pytest.mark.integration

FILLER = " ".join(["We help families and employers with UK immigration."] * 30)
HOME = f"""<!doctype html><html lang="en"><head><title>Bright Legal | Immigration solicitors</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://www.googletagmanager.com/gtag/js?id=G-TEST"></script></head>
<body><h1>Immigration solicitors in London</h1><p>{FILLER}</p>
<p>Spouse visas, skilled worker visas and sponsor licences.</p>
<a href="/contact/">Contact</a> <a href="/about-us/">About</a>
<footer>© 2018 Bright Legal Ltd. Regulated by the Solicitors Regulation Authority.</footer>
</body></html>"""
CONTACT = f"""<html><head><title>Contact</title></head><body><h1>Contact us</h1><p>{FILLER}</p>
<form><input name="name"><input type="email" name="email"><textarea name="message"></textarea>
</form></body></html>"""
ABOUT = (
    f"<html><head><title>About</title></head><body><h1>About us</h1><p>{FILLER}</p></body></html>"
)
PAGES = {"/": HOME, "/contact/": CONTACT, "/about-us/": ABOUT}
CDX_FIRST = [["timestamp"], ["20110304000000"]]
CDX_RECENT = [["timestamp", "digest"], ["20180101000000", "A"], ["20190910000000", "B"]]
cdx_queries: list[dict[str, list[str]]] = []


@pytest.fixture
def port() -> Iterator[int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            host = (self.headers.get("Host") or "").split(":")[0]
            path = urlsplit(self.path)
            if host == "wa.test" and path.path == "/cdx":
                query = parse_qs(path.query)
                cdx_queries.append(query)
                rows = CDX_RECENT if "collapse" in query else CDX_FIRST
                ctype, body = "application/json", json.dumps(rows)
            elif host == "brightlegal.test" and path.path in PAGES:
                ctype, body = "text/html", PAGES[path.path]
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
    cdx_queries.clear()
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


def test_research_finds_compliance_gaps_and_site_age_and_raises_an_opportunity(
    engine: Engine, settings: Settings, port: int
) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_enqueuer] = lambda: lambda _run_id: None
    make_user(engine, "m@verkies.test", ["sales_manager"])
    with TestClient(app) as http:
        client = ApiClient(http)
        client.login("m@verkies.test")
        run = client.send(
            "POST", "/research-runs", json={"url": f"http://brightlegal.test:{port}/"}
        ).json()
        run_pipeline(
            uuid.UUID(run["id"]),
            settings,
            render=False,
            hosts=("brightlegal.test", "wa.test"),
            site_checks=SiteChecks(Wayback(base_url=f"http://wa.test:{port}/cdx")),
        )

        detail = client.get(f"/research-runs/{run['id']}").json()
        assert detail["status"] == "completed", detail
        enrich = next(s for s in detail["stages"] if s["stage"] == "enrich")["detail"]
        assert enrich["website_archive"] == "last changed 2019-09-10"
        assert {q["url"][0] for q in cdx_queries} == {"brightlegal.test"}

        areas = client.get(f"/research-runs/{run['id']}/intelligence").json()["areas"]
        compliance = {o["key"]: o for o in areas["compliance"]}
        assert compliance["compliance.sra_regulated"]["value"] is True
        for key in (
            "compliance.sra_badge",
            "compliance.sra_number",
            "compliance.complaints_procedure",
            "compliance.company_number_shown",
        ):
            assert compliance[key]["value"] is False, key
            assert "pages crawled" in compliance[key]["evidence"]["excerpt"]
        assert compliance["compliance.price_information"]["value"] == {
            "service": "immigration",
            "published": False,
        }
        assert compliance["compliance.cookie_consent"]["value"] == {
            "trackers": ["Google Analytics"],
            "consent_tool": None,
        }
        archive = next(o for o in areas["website"] if o["key"] == "website.archive")
        assert archive["value"]["last_changed"] == "2019-09-10"
        assert archive["value"]["first_captured"] == "2011-03-04"
        assert archive["evidence"]["source_url"] == "https://web.archive.org/web/*/brightlegal.test"

        opportunities = client.get(f"/research-runs/{run['id']}/assessment").json()["opportunities"]
        fixes = next(o for o in opportunities if o["rule_key"] == "website_rebuild.compliance_gaps")
        assert fixes["title"] == "Website compliance fixes"
        assert "no SRA digital badge" in fixes["problem"]
        cited = {e["excerpt"] for e in fixes["evidence"]}
        assert any("No SRA digital badge" in text for text in cited)
        rebuild = next(
            o for o in opportunities if o["rule_key"] == "website_rebuild.neglect_signals"
        )
        assert "(Wayback Machine)" in rebuild["problem"]
