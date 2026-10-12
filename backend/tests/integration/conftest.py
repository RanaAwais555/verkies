"""Integration fixtures: a migrated database, cleaned between tests, and API helpers.

Setup and assertions use a synchronous engine so they never share a connection pool with the
app, whose async engine lives in the TestClient's event loop.
"""

import json
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urlencode

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text

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
    "pipelines",
    "pipeline_stages",
}


def _seed_configs() -> tuple[dict, dict]:  # type: ignore[type-arg]
    """Version-1 configs exactly as migration 0006 seeds them."""
    import importlib.util

    path = os.path.join(BACKEND_DIR, "alembic", "versions", "0006_default_configs.py")
    spec = importlib.util.spec_from_file_location("seed_0006", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ICP_V1, module.SCORING_V1


def _seed_views() -> list[tuple[str, str, dict[str, str]]]:
    """The team's saved views exactly as migration 0016 seeds them."""
    import importlib.util

    path = os.path.join(BACKEND_DIR, "alembic", "versions", "0016_reports_and_saved_views.py")
    spec = importlib.util.spec_from_file_location("seed_0016", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.TEAM_VIEWS)


def _seed_outreach(conn: Connection) -> None:
    """The default outreach templates and sequence exactly as migration 0018 seeds them."""
    import importlib.util

    path = os.path.join(BACKEND_DIR, "alembic", "versions", "0018_outreach.py")
    spec = importlib.util.spec_from_file_location("seed_0018", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed_default_sequence(conn)


def _load_migration(filename: str):  # type: ignore[no-untyped-def]
    import importlib.util

    path = os.path.join(BACKEND_DIR, "alembic", "versions", filename)
    spec = importlib.util.spec_from_file_location(f"seed_{filename[:4]}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        # Configs reference users, so the cascade empties them: restore the seeded version 1.
        icp, scoring = _seed_configs()
        for table, config in (("icp_configs", icp), ("scoring_configs", scoring)):
            conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608
            conn.execute(
                text(
                    f"INSERT INTO {table} (id, version, is_active, config, note)"  # noqa: S608
                    " VALUES (gen_random_uuid(), 1, true, CAST(:c AS jsonb), 'seed')"
                ),
                {"c": json.dumps(config)},
            )
        # Saved views reference users too: restore the team views migration 0016 seeds.
        for position, (name, path, query) in enumerate(_seed_views()):
            conn.execute(
                text(
                    "INSERT INTO saved_views (id, user_id, name, path, query, position)"
                    " VALUES (gen_random_uuid(), NULL, :n, :p, :q, :pos)"
                ),
                {"n": name, "p": path, "q": urlencode(query), "pos": position},
            )
        # Outreach templates and sequences reference users as well.
        _seed_outreach(conn)
        # And the client views of migration 0020.
        _load_migration("0020_client_health.py").seed_client_views(conn)
        _load_migration("0021_expansion_and_referrals.py").seed_expansion_views(conn)


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
