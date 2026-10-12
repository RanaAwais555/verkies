"""Slice 7.1: Prometheus metrics on the internal port."""

import uuid
from collections.abc import Iterator

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.config import get_settings
from app.main import create_app
from app.observability import worker
from tests.integration.conftest import ApiClient, make_user

pytestmark = pytest.mark.integration

INTERNAL = {"host": "localhost"}


@pytest.fixture
def worker_keys() -> Iterator[redis.Redis]:
    client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    client.delete(worker.TASKS_KEY, worker.LAST_SUCCESS_KEY)
    yield client
    client.delete(worker.TASKS_KEY, worker.LAST_SUCCESS_KEY)


def scrape(api: ApiClient) -> str:
    response = api.http.get("/metrics", headers=INTERNAL)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    return response.text


def test_metrics_are_only_answered_on_internal_hostnames(api: ApiClient) -> None:
    assert api.http.get("/metrics").status_code == 404  # "testserver", like a public name
    assert api.http.get("/metrics", headers={"host": "vros.verkies.co"}).status_code == 404
    assert api.http.get("/metrics", headers={"host": "api:8000"}).status_code == 200


def test_requests_are_counted_by_route_template_not_raw_path(
    engine: Engine, api: ApiClient
) -> None:
    make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    missing = uuid.uuid4()
    assert api.get(f"/accounts/{missing}").status_code == 404
    body = scrape(api)
    line = 'vros_http_requests_total{method="GET",route="/accounts/{account_id}",status="404"}'
    assert f"{line} 1.0" in body
    assert str(missing) not in body
    assert 'vros_http_request_duration_seconds_count{method="GET"' in body
    assert 'route="/metrics"' not in body
    assert "_created" not in body


def test_work_in_hand_and_worker_outcomes(
    engine: Engine, api: ApiClient, worker_keys: redis.Redis
) -> None:
    owner = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    with engine.begin() as conn:
        for status, review in (
            ("queued", "pending"),
            ("queued", "pending"),
            ("completed", "pending"),
        ):
            conn.execute(
                text(
                    "INSERT INTO research_runs (id, input_url, normalised_domain, requested_by_id,"
                    " status, review_status, retry_count, crawl_budget, possible_duplicate_of)"
                    " VALUES (gen_random_uuid(), 'https://a.test/', 'a.test', :u, :s, :r, 0,"
                    " '{}', '[]')"
                ),
                {"u": owner, "s": status, "r": review},
            )
    worker.record("vros.monitoring.check_watched", "success", 2.5)
    worker.record("vros.monitoring.check_watched", "failure")

    body = scrape(api)
    assert 'vros_research_runs{status="queued"} 2.0' in body
    assert 'vros_research_runs{status="running"} 0.0' in body
    assert "vros_review_queue 1.0" in body
    assert "vros_monitor_alerts_open 0.0" in body
    assert "vros_tasks_overdue 0.0" in body
    assert 'vros_dependency_up{dependency="database"} 1.0' in body
    assert 'vros_dependency_up{dependency="redis"} 1.0' in body
    assert "vros_celery_queue_length " in body
    task = 'task="vros.monitoring.check_watched"'
    assert f'vros_worker_tasks{{state="success",{task}}} 1.0' in body
    assert f'vros_worker_tasks{{state="failure",{task}}} 1.0' in body
    assert f"vros_worker_task_seconds{{{task}}} 2.5" in body
    assert f"vros_worker_task_last_success_timestamp_seconds{{{task}}}" in body


def test_metrics_can_be_switched_off() -> None:
    settings = get_settings().model_copy(update={"metrics_enabled": False})
    with TestClient(create_app(settings)) as http:
        assert http.get("/metrics", headers=INTERNAL).status_code == 404
