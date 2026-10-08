import os
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.providers.fetch.netguard import parse_networks
from app.providers.fetch.render import PlaywrightRenderer
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.fetch.types import FetchBudget
from tests.unit.test_netguard import FakeResolver

# CI installs Chromium with `playwright install` and sets VROS_TEST_CHROMIUM=playwright, meaning
# "use Playwright's own browser". Locally a pre-installed headless shell is used if present.
_SANDBOX_SHELL = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"
_CONFIGURED = os.environ.get("VROS_TEST_CHROMIUM", _SANDBOX_SHELL)
CHROMIUM_AVAILABLE = _CONFIGURED == "playwright" or os.path.exists(_CONFIGURED)
CHROMIUM: str | None = None if _CONFIGURED == "playwright" else _CONFIGURED
pytestmark = pytest.mark.skipif(not CHROMIUM_AVAILABLE, reason="Chromium not installed")

PAGE = b"""<!doctype html><html><head><title>Shell</title>
<script src="/app.js" defer></script></head><body><div id="root"></div></body></html>"""
SCRIPT = b"""
const root = document.getElementById('root');
root.innerHTML = '<h1>Rendered by JavaScript</h1><a href="/pricing">Pricing</a>';
fetch('http://169.254.169.254/latest/meta-data/')
  .then(() => { document.title = 'LEAKED'; })
  .catch(() => {});
fetch('/api/track', {method: 'POST', body: 'x'}).catch(() => {});
try { new WebSocket('ws://' + location.host + '/ws'); } catch (e) {}
"""


@pytest.fixture
def site() -> Iterator[tuple[int, list[str]]]:
    hits: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hits.append(f"GET {self.path}")
            if self.path == "/old":
                self.send_response(301)
                self.send_header("Location", "/")
                self.end_headers()
                return
            body, kind = (
                (SCRIPT, "text/javascript") if self.path == "/app.js" else (PAGE, "text/html")
            )
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            hits.append(f"POST {self.path}")
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], hits
    server.shutdown()


def _renderer(port: int) -> tuple[PlaywrightRenderer, SafeHttpFetcher]:
    fetcher = SafeHttpFetcher(
        user_agent="VROSBot/test",
        budget=FetchBudget(allowed_ports=frozenset({port, 80, 443})),
        resolver=FakeResolver({"site.test": ["127.0.0.1"]}),
        allowlist=parse_networks(["127.0.0.0/8"]),  # the test site only; metadata stays blocked
    )
    return PlaywrightRenderer(fetcher, executable=CHROMIUM, timeout_seconds=20), fetcher


async def test_renders_javascript_through_the_safe_fetcher(site: tuple[int, list[str]]) -> None:
    port, hits = site
    renderer, fetcher = _renderer(port)
    result = await renderer.render(f"http://site.test:{port}/")
    await fetcher.aclose()
    assert "Rendered by JavaScript" in result.html
    assert "LEAKED" not in result.html
    assert any("169.254.169.254" in b for b in result.blocked)
    assert not any(h.startswith("POST") for h in hits)  # no data is ever sent
    assert hits.count("GET /app.js") == 1


async def test_navigation_redirects_are_visible_to_the_page(site: tuple[int, list[str]]) -> None:
    port, _ = site
    renderer, fetcher = _renderer(port)
    result = await renderer.render(f"http://site.test:{port}/old")
    await fetcher.aclose()
    assert result.final_url == f"http://site.test:{port}/"
    assert "Rendered by JavaScript" in result.html
