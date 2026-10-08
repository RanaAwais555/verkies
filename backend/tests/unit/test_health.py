import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.health.router import HealthCheck, get_health_checks
from app.main import REQUEST_ID_HEADER, create_app


async def _ok() -> None:
    return None


async def _refused() -> None:
    raise ConnectionRefusedError("postgresql://vros:secret@db:5432 refused")


async def _hang() -> None:
    await asyncio.sleep(10)


def _client(checks: dict[str, HealthCheck], **settings_kwargs: Any) -> TestClient:
    settings = Settings(_env_file=None, health_check_timeout=0.05, **settings_kwargs)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_health_checks] = lambda: checks
    return TestClient(app)


@pytest.fixture
def healthy() -> Iterator[TestClient]:
    with _client({"database": _ok, "redis": _ok}) as client:
        yield client


def test_live_reports_version(healthy: TestClient) -> None:
    response = healthy.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_ready_ok_when_all_dependencies_ok(healthy: TestClient) -> None:
    response = healthy.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {
            "database": {"status": "ok", "error": None},
            "redis": {"status": "ok", "error": None},
        },
    }


def test_ready_503_and_no_secret_leak_when_a_dependency_fails() -> None:
    with _client({"database": _refused, "redis": _ok}) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "down"
    assert body["checks"]["database"] == {"status": "down", "error": "ConnectionRefusedError"}
    assert body["checks"]["redis"]["status"] == "ok"
    assert "secret" not in response.text


def test_ready_treats_a_hung_dependency_as_down() -> None:
    with _client({"database": _ok, "redis": _hang}) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["redis"] == {"status": "down", "error": "timeout"}


def test_request_id_is_echoed(healthy: TestClient) -> None:
    response = healthy.get("/api/v1/health/live", headers={REQUEST_ID_HEADER: "abc-123"})
    assert response.headers[REQUEST_ID_HEADER] == "abc-123"


@pytest.mark.parametrize("incoming", [None, "", "x" * 65])
def test_request_id_is_minted_when_missing_or_invalid(
    healthy: TestClient, incoming: str | None
) -> None:
    headers = {REQUEST_ID_HEADER: incoming} if incoming is not None else {}
    rid = healthy.get("/api/v1/health/live", headers=headers).headers[REQUEST_ID_HEADER]
    assert rid != incoming
    assert len(rid) == 32


def test_docs_served_outside_production(healthy: TestClient) -> None:
    assert healthy.get("/api/v1/openapi.json").status_code == 200


PROD = {
    "environment": "production",
    "public_url": "https://vros.example.com",
    "secret_key": "x" * 32,
    "database_url": "postgresql+psycopg://vros:s3cure-pass@postgres:5432/vros",
}


def test_production_hides_docs_and_rejects_foreign_hosts() -> None:
    with _client({"database": _ok, "redis": _ok}, **PROD) as client:
        assert (
            client.get("/api/v1/openapi.json", headers={"Host": "vros.example.com"}).status_code
            == 404
        )
        assert (
            client.get("/api/v1/health/live", headers={"Host": "vros.example.com"}).status_code
            == 200
        )
        assert client.get("/api/v1/health/live", headers={"Host": "localhost"}).status_code == 200
        assert client.get("/api/v1/health/live", headers={"Host": "api:8000"}).status_code == 200
        assert client.get("/api/v1/health/live", headers={"Host": "evil.test"}).status_code == 400
