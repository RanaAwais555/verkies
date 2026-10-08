import pytest
from fastapi.testclient import TestClient

from app.main import create_app

pytestmark = pytest.mark.integration


def test_ready_against_real_postgres_and_redis() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"
