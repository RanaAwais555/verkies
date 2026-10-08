"""Integration fixtures: a migrated database, cleaned between tests, and API helpers.

Setup and assertions use a synchronous engine so they never share a connection pool with the
app, whose async engine lives in the TestClient's event loop.
"""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from alembic import command
from app.auth.passwords import hash_password
from app.config import get_settings
from app.main import create_app

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
PASSWORD = "correct horse battery staple"  # noqa: S105 - test fixture

# Reference data seeded by migrations; everything else is wiped between tests.
SEED_TABLES = {
    "alembic_version",
    "roles",
    "permissions",
    "role_permissions",
    "opportunity_categories",
    "services",
    "reference_projects",
    "reference_project_services",
}


def alembic_config(url: str) -> Config:
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.attributes["database_url"] = url
    return config


@pytest.fixture(scope="session")
def database_url() -> str:
    return get_settings().database_url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    eng = create_engine(database_url)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(database_url), "head")
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean_db(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as conn:
        tables = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
        mutable = [t for t in tables if t not in SEED_TABLES]
        if mutable:
            conn.execute(text(f"TRUNCATE {', '.join(mutable)} CASCADE"))


def make_user(
    engine: Engine,
    email: str,
    roles: list[str],
    *,
    password: str = PASSWORD,
    name: str = "Test User",
    is_active: bool = True,
) -> uuid.UUID:
    user_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, name, password_hash, is_active, failed_login_count)"
                " VALUES (:id, :e, :n, :h, :a, 0)"
            ),
            {"id": user_id, "e": email, "n": name, "h": hash_password(password), "a": is_active},
        )
        conn.execute(
            text(
                "INSERT INTO user_roles (user_id, role_id) "
                "SELECT :id, id FROM roles WHERE key = ANY(:roles)"
            ),
            {"id": user_id, "roles": roles},
        )
    return user_id


@dataclass
class ApiClient:
    """A TestClient that signs in and sends the CSRF header automatically."""

    http: TestClient
    csrf: str = ""

    def login(self, email: str, password: str = PASSWORD) -> dict:  # type: ignore[type-arg]
        response = self.http.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        self.csrf = response.json()["csrf_token"]
        return response.json()

    def get(self, path: str, **kw):  # type: ignore[no-untyped-def]
        return self.http.get(f"/api/v1{path}", **kw)

    def send(self, method: str, path: str, **kw):  # type: ignore[no-untyped-def]
        headers = {"X-CSRF-Token": self.csrf, **kw.pop("headers", {})}
        return self.http.request(method, f"/api/v1{path}", headers=headers, **kw)


@pytest.fixture
def api(engine: Engine) -> Iterator[ApiClient]:
    with TestClient(create_app()) as http:
        yield ApiClient(http)


@pytest.fixture
def make_api(engine: Engine) -> Iterator[object]:
    """Factory for extra independent clients (e.g. a second browser)."""
    clients: list[TestClient] = []

    def factory() -> ApiClient:
        http = TestClient(create_app())
        http.__enter__()
        clients.append(http)
        return ApiClient(http)

    yield factory
    for http in clients:
        http.__exit__(None, None, None)
