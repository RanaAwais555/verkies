import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("VROS_ENVIRONMENT", "test")
# No calls to the breached-password service from tests; tests that need it use a fake.
os.environ.setdefault("VROS_BREACHED_PASSWORD_CHECK", "false")
# Nor to the Wayback Machine from research runs; tests that need it use a fake.
os.environ.setdefault("VROS_WEBSITE_ARCHIVE_ENABLED", "false")

from app.config import get_settings
from app.db import get_engine, get_sessionmaker


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    """Each test sees settings built from its own environment, not a cached copy."""
    for cached in (get_settings, get_engine, get_sessionmaker):
        cached.cache_clear()
    yield
    for cached in (get_settings, get_engine, get_sessionmaker):
        cached.cache_clear()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("VROS_RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="set VROS_RUN_INTEGRATION=1 with PostgreSQL and Redis running")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
