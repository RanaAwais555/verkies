import gzip
import ssl
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
import trustme

from app.providers.fetch.netguard import parse_networks
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.fetch.types import FetchBlocked, FetchBudget, FetchFailed
from tests.unit.test_netguard import FakeResolver

PUBLIC = "93.184.216.34"
UA = "VROSBot/test"


def _fetcher(
    handler: Callable[[httpx.Request], httpx.Response],
    resolver: FakeResolver | None = None,
    **budget: object,
) -> SafeHttpFetcher:
    return SafeHttpFetcher(
        user_agent=UA,
        budget=FetchBudget(**budget),  # type: ignore[arg-type]
        resolver=resolver or FakeResolver({"site.test": [PUBLIC]}),
        transport=httpx.MockTransport(handler),
    )


def _html(body: str = "<html><title>x</title></html>", status: int = 200) -> httpx.Response:
    return httpx.Response(status, headers={"content-type": "text/html; charset=utf-8"}, text=body)


async def test_connects_to_pinned_ip_with_real_host_and_sni() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _html()

    async with _fetcher(handler) as fetcher:
        result = await fetcher.fetch("https://site.test/about?x=1")
    request = seen[0]
    assert request.url.host == PUBLIC
    assert request.headers["host"] == "site.test"
    assert request.extensions["sni_hostname"] == "site.test"
    assert request.headers["user-agent"] == UA
    assert result.final_url == "https://site.test/about?x=1"
    assert result.is_html and result.status == 200


async def test_dns_rebinding_cannot_redirect_the_connection() -> None:
    class Rebinding(FakeResolver):
        async def resolve(self, host: str, port: int) -> list[str]:
            self.calls.append(host)
            return [PUBLIC] if len(self.calls) == 1 else ["127.0.0.1"]

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return _html()

    resolver = Rebinding({})
    async with _fetcher(handler, resolver) as fetcher:
        await fetcher.fetch("https://site.test/")
        with pytest.raises(FetchBlocked):  # a later lookup that rebinds is refused
            await fetcher.fetch("https://site.test/again")
    assert seen == [PUBLIC]


async def test_redirect_to_internal_address_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    async with _fetcher(handler) as fetcher:
        with pytest.raises(FetchBlocked) as caught:
            await fetcher.fetch("https://site.test/")
    assert caught.value.code == "non_public_address"


async def test_redirects_are_followed_and_recorded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return _html()

    async with _fetcher(handler) as fetcher:
        result = await fetcher.fetch("https://site.test/old")
    assert result.final_url == "https://site.test/new"
    assert result.redirects == ["https://site.test/new"]


async def test_redirect_loops_are_capped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    async with _fetcher(handler, max_redirects=3) as fetcher:
        with pytest.raises(FetchBlocked) as caught:
            await fetcher.fetch("https://site.test/loop")
    assert caught.value.code == "too_many_redirects"


async def test_oversized_body_is_cut_off() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"a" * 5000)

    async with _fetcher(handler, max_bytes=1000) as fetcher:
        with pytest.raises(FetchBlocked) as caught:
            await fetcher.fetch("https://site.test/")
    assert caught.value.code == "too_large"


async def test_decompression_bomb_is_measured_after_decoding() -> None:
    bomb = gzip.compress(b"a" * 1_000_000)  # ~1 KB on the wire

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html", "content-encoding": "gzip"}, content=bomb
        )

    assert len(bomb) < 5000
    async with _fetcher(handler, max_bytes=100_000) as fetcher:
        with pytest.raises(FetchBlocked) as caught:
            await fetcher.fetch("https://site.test/")
    assert caught.value.code == "too_large"


async def test_unexpected_content_type_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/zip"}, content=b"PK")

    async with _fetcher(handler) as fetcher:
        with pytest.raises(FetchBlocked) as caught:
            await fetcher.fetch("https://site.test/file.zip")
    assert caught.value.code == "bad_content_type"


async def test_environment_proxies_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://10.0.0.1:3128")
    async with _fetcher(lambda r: _html()) as fetcher:
        assert fetcher._client._trust_env is False


# --- real sockets: TLS verification and timeouts ------------------------------------------


@pytest.fixture
def tls_server() -> Iterator[tuple[int, trustme.CA]]:
    ca = trustme.CA()
    cert = ca.issue_cert("site.test")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = f"host={self.headers['Host']}".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    cert.configure_cert(context)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1], ca
    server.shutdown()


def _real_fetcher(port: int, ca: trustme.CA, host: str = "site.test") -> SafeHttpFetcher:
    client_ctx = ssl.create_default_context()
    ca.configure_trust(client_ctx)
    return SafeHttpFetcher(
        user_agent=UA,
        budget=FetchBudget(allowed_ports=frozenset({port})),
        resolver=FakeResolver({host: ["127.0.0.1"]}),
        allowlist=parse_networks(["127.0.0.0/8"]),
        verify=client_ctx,
    )


async def test_pinned_https_still_verifies_the_certificate_hostname(
    tls_server: tuple[int, trustme.CA],
) -> None:
    port, ca = tls_server
    async with _real_fetcher(port, ca) as fetcher:
        result = await fetcher.fetch(f"https://site.test:{port}/")
    assert result.text() == f"host=site.test:{port}"
    # Same IP, but the certificate is not valid for this name: refused.
    async with _real_fetcher(port, ca, host="other.test") as fetcher:
        with pytest.raises(FetchFailed):
            await fetcher.fetch(f"https://other.test:{port}/")


async def test_slow_drip_server_hits_the_deadline() -> None:
    import socket
    import time

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]

    def drip() -> None:
        conn, _ = listener.accept()
        conn.recv(1024)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
        for _ in range(30):
            try:
                conn.sendall(b"a")
            except OSError:
                break
            time.sleep(0.2)
        conn.close()

    threading.Thread(target=drip, daemon=True).start()
    fetcher = SafeHttpFetcher(
        user_agent=UA,
        budget=FetchBudget(allowed_ports=frozenset({port}), timeout_seconds=1.0),
        resolver=FakeResolver({"slow.test": ["127.0.0.1"]}),
        allowlist=parse_networks(["127.0.0.0/8"]),
    )
    started = time.monotonic()
    with pytest.raises(FetchFailed) as caught:
        await fetcher.fetch(f"http://slow.test:{port}/")
    await fetcher.aclose()
    listener.close()
    assert caught.value.code == "timeout"
    assert time.monotonic() - started < 3


async def test_error_responses_report_status_without_downloading() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"content-type": "application/zip"}, content=b"x" * 10)

    async with _fetcher(handler, max_bytes=5) as fetcher:
        result = await fetcher.fetch("https://site.test/sitemap.xml")
    assert result.status == 404 and result.body == b""
