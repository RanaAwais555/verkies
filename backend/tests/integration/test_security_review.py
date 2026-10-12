"""Slice 7.3: rate limits and the breached-password check."""

import hashlib
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import Engine

from app.config import get_settings
from app.security import breached
from tests.integration.conftest import PASSWORD, ApiClient, make_user

pytestmark = pytest.mark.integration


def configure(monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
    for name, value in values.items():
        monkeypatch.setenv(f"VROS_{name.upper()}", value)
    get_settings.cache_clear()


def test_sign_in_is_limited_per_client_address(
    engine: Engine, api: ApiClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    configure(monkeypatch, {"rate_limit_login_per_ip": "3"})
    for _ in range(3):
        wrong = {"email": f"nobody{_}@verkies.test", "password": "not the password at all"}
        assert api.http.post("/api/v1/auth/login", json=wrong).status_code == 401
    # Spraying other accounts from the same address stops; so does the right password.
    blocked = api.http.post(
        "/api/v1/auth/login", json={"email": "ada@verkies.test", "password": PASSWORD}
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert 0 < int(blocked.headers["Retry-After"]) <= 600
    assert blocked.json()["error"]["details"]["retry_after"] == int(blocked.headers["Retry-After"])


def test_invite_links_are_limited_per_client_address(
    api: ApiClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, {"rate_limit_invite_per_ip": "2"})
    guess = {"token": "x" * 43}
    assert api.http.post("/api/v1/auth/invites/inspect", json=guess).status_code != 429
    assert api.http.post("/api/v1/auth/invites/inspect", json=guess).status_code != 429
    assert api.http.post("/api/v1/auth/invites/inspect", json=guess).status_code == 429
    accept = {"token": "x" * 43, "name": "Eve", "password": "a long enough password"}
    assert api.http.post("/api/v1/auth/invites/accept", json=accept).status_code == 429


def test_api_requests_and_password_changes_are_limited_per_person(
    engine: Engine, api: ApiClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    configure(
        monkeypatch, {"rate_limit_api_per_minute": "4", "rate_limit_password_changes_per_hour": "1"}
    )
    codes = [api.get("/auth/me").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 200, 429]

    configure(monkeypatch, {"rate_limit_api_per_minute": "1000"})
    change = {"current_password": "wrong wrong wrong", "new_password": "another long password"}
    assert api.send("POST", "/auth/password", json=change).status_code != 429
    assert api.send("POST", "/auth/password", json=change).status_code == 429


def test_limits_let_requests_through_when_redis_is_down(
    engine: Engine, api: ApiClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    # Rate limits read VROS_REDIS_URL per request; nothing listens on this port.
    configure(monkeypatch, {"rate_limit_api_per_minute": "1", "redis_url": "redis://127.0.0.1:1/0"})
    assert [api.get("/auth/me").status_code for _ in range(3)] == [200, 200, 200]


@pytest.fixture
def pwned(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """A fake range API that knows one breached password; records what was asked."""
    asked: list[str] = []
    leaked = hashlib.sha1(b"password1234567", usedforsecurity=False).hexdigest().upper()

    def handler(request: httpx.Request) -> httpx.Response:
        prefix = request.url.path.rsplit("/", 1)[-1]
        asked.append(prefix)
        assert request.headers["Add-Padding"] == "true"
        if prefix == "FAIL0":
            return httpx.Response(503)
        body = "0018A45C4D1DEF81644B54AB7F969B88D65:1\r\n"
        if prefix == leaked[:5]:
            body += f"{leaked[5:]}:24230577\r\n"
        return httpx.Response(200, text=body)

    monkeypatch.setattr(breached, "transport", httpx.MockTransport(handler))
    configure(monkeypatch, {"breached_password_check": "true"})
    yield asked


def test_breached_passwords_are_refused_and_only_a_hash_prefix_is_sent(
    engine: Engine, api: ApiClient, pwned: list[str]
) -> None:
    make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    change = {"current_password": PASSWORD, "new_password": "password1234567"}
    refused = api.send("POST", "/auth/password", json=change)
    assert refused.status_code == 422
    assert "24,230,577 times in known data breaches" in refused.json()["error"]["message"]
    assert all(len(prefix) == 5 for prefix in pwned)  # never the password or its full hash

    fine = {"current_password": PASSWORD, "new_password": "a sentence nobody has leaked yet"}
    assert api.send("POST", "/auth/password", json=fine).status_code == 204


async def test_an_unreachable_breach_service_does_not_block_anyone(
    pwned: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    monkeypatch.setattr(breached, "transport", httpx.MockTransport(down))
    assert await breached.times_breached("anything at all here") is None
    await breached.check_not_breached("anything at all here")  # does not raise
