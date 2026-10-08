"""Serves the fixture websites over HTTP for local end-to-end runs, chosen by Host header.

    python -m tests.fixtures.serve 8090

Point the crawler at it with VROS_FETCH_HOST_OVERRIDES=harbour.test=127.0.0.1,... and
VROS_FETCH_PRIVATE_ALLOWLIST=127.0.0.0/8 (development only; refused in production).
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests.fixtures.sites import (
    AGENCY,
    CLOSED,
    IMMIGRATION_ABOUT,
    IMMIGRATION_CONTACT,
    IMMIGRATION_HOME,
    IMMIGRATION_TEAM,
)

SITES = {
    "harbour.test": {
        "/": IMMIGRATION_HOME,
        "/contact/": IMMIGRATION_CONTACT,
        "/our-team/": IMMIGRATION_TEAM,
        "/about-us/": IMMIGRATION_ABOUT,
    },
    "pixelforge.test": {"/": AGENCY[0][0].html},
    "oldmill.test": {"/": CLOSED[0][0].html},
}


def _search_results(port: int) -> bytes:
    """A stand-in for SearXNG's JSON API (VROS_SEARXNG_URL pointed at this server)."""
    results = [
        {"url": f"http://harbour.test:{port}/about-us/", "title": "Harbour Immigration | Visas"},
        {"url": f"http://pixelforge.test:{port}/", "title": "Pixelforge - Digital Agency"},
        {"url": "https://uk.linkedin.com/company/harbour", "title": "Harbour | LinkedIn"},
    ]
    return json.dumps({"results": results}).encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if self.path.startswith("/search?"):
            body = _search_results(self.server.server_address[1])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        page = SITES.get(host, {}).get(self.path)
        if page is None:
            self.send_response(404)
            self.end_headers()
            return
        body = page.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"fixture sites on http://127.0.0.1:{port} ({', '.join(SITES)})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
