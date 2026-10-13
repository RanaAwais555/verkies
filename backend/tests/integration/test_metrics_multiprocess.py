"""Slice 7.5: with several API processes, /metrics counts every process's requests."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

# Each run is its own Python process, as each uvicorn worker is.
REQUEST = """
from fastapi.testclient import TestClient
from app.main import create_app
with TestClient(create_app()) as http:
    assert http.get("/api/v1/health/live").status_code == 200
"""
SCRAPE = """
from fastapi.testclient import TestClient
from app.main import create_app
with TestClient(create_app()) as http:
    print(http.get("/metrics", headers={"host": "localhost"}).text)
"""


def run(code: str, env: dict[str, str]) -> str:
    done = subprocess.run(  # noqa: S603 - our own fixed code, run by the test interpreter
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    )
    return done.stdout


def test_requests_from_every_process_are_counted(tmp_path: Path) -> None:
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}
    run(REQUEST, env)
    run(REQUEST, env)
    body = run(SCRAPE, env)
    line = 'vros_http_requests_total{method="GET",route="/health/live",status="200"}'
    assert f"{line} 2.0" in body
    assert "vros_dependency_up" in body  # the live gauges are still there
    assert len(list(tmp_path.iterdir())) >= 2  # one file per process
