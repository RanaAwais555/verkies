"""Prometheus metrics (master context §17 Monitoring and logs; slice 7.1).

GET /metrics on the API's internal port, in the Prometheus text format. It is answered only for
the internal hostnames (Prometheus on the Docker network, or localhost): Caddy forwards only
/api/* to the API, and a request that reaches /metrics under the public hostname gets a 404.

- HTTP: requests and their duration by method, route template and status.
- Work in hand, read when scraped: research runs queued or running, prospects waiting for
  review, open monitoring alerts, overdue tasks, jobs waiting in the Celery queue.
- The worker: task successes, failures, retries and time spent, and when each task last
  succeeded (app.observability.worker), so a daily job that stops running can raise an alert.

Counts only: no names, emails, URLs or other personal data are ever labels.
"""

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    disable_created_metrics,
    generate_latest,
)
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from sqlalchemy import func, select

from app.config import Settings
from app.core.enums import JobStatus, ReviewStatus, RunKind, TaskStatus
from app.crm.models import Task
from app.db import get_sessionmaker
from app.monitoring.models import MonitorAlert
from app.observability.worker import LAST_SUCCESS_KEY, TASKS_KEY
from app.research.models import ResearchRun

METRICS_PATH = "/metrics"
CELERY_QUEUE = "celery"
# The *_created series only add noise here.
disable_created_metrics()  # type: ignore[no-untyped-call]

BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)


class HttpMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "vros_http_requests",
            "HTTP requests answered by the API.",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "vros_http_request_duration_seconds",
            "Time to answer an HTTP request.",
            ["method", "route"],
            buckets=BUCKETS,
            registry=self.registry,
        )

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        self.requests.labels(method, route, str(status)).inc()
        self.duration.labels(method, route).observe(seconds)


def route_of(request: Request) -> str:
    """The route template (/accounts/{account_id}), never the raw path with its IDs."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


async def live_metrics(settings: Settings) -> bytes:
    """Gauges read now from the database and Redis."""
    registry = CollectorRegistry()

    def gauge(name: str, doc: str, labels: tuple[str, ...] = ()) -> Gauge:
        return Gauge(name, doc, list(labels), registry=registry)

    up = gauge("vros_dependency_up", "1 when the API could read the dependency.", ("dependency",))
    try:
        async with get_sessionmaker()() as db:
            runs = gauge("vros_research_runs", "Research runs in progress.", ("status",))
            counts = dict(
                (
                    await db.execute(
                        select(ResearchRun.status, func.count())
                        .where(
                            ResearchRun.kind == RunKind.RESEARCH,
                            ResearchRun.status.in_(
                                [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING]
                            ),
                        )
                        .group_by(ResearchRun.status)
                    )
                ).all()
            )
            for status in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING):
                runs.labels(status.value).set(counts.get(status, 0))
            gauge("vros_review_queue", "Researched prospects waiting for review.").set(
                (
                    await db.execute(
                        select(func.count()).where(
                            ResearchRun.kind == RunKind.RESEARCH,
                            ResearchRun.status == JobStatus.COMPLETED,
                            ResearchRun.review_status == ReviewStatus.PENDING,
                        )
                    )
                ).scalar_one()
            )
            gauge("vros_monitor_alerts_open", "Monitoring alerts not yet reviewed.").set(
                (
                    await db.execute(select(func.count()).where(MonitorAlert.reviewed_at.is_(None)))
                ).scalar_one()
            )
            gauge("vros_tasks_overdue", "Open tasks past their due time.").set(
                (
                    await db.execute(
                        select(func.count()).where(
                            Task.deleted_at.is_(None),
                            Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
                            Task.due_at < datetime.now(UTC),
                        )
                    )
                ).scalar_one()
            )
        up.labels("database").set(1)
    except Exception:
        up.labels("database").set(0)

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        gauge("vros_celery_queue_length", "Jobs waiting for a worker.").set(
            await client.llen(CELERY_QUEUE)
        )
        tasks = await client.hgetall(TASKS_KEY)
        last = await client.hgetall(LAST_SUCCESS_KEY)
        outcomes = gauge(
            "vros_worker_tasks", "Worker task outcomes since Redis was reset.", ("task", "state")
        )
        seconds = gauge(
            "vros_worker_task_seconds", "Time worker tasks have spent running.", ("task",)
        )
        for key, value in tasks.items():
            task, _, state = str(key).rpartition("|")
            if state == "seconds":
                seconds.labels(task).set(float(value))
            else:
                outcomes.labels(task, state).set(float(value))
        success = gauge(
            "vros_worker_task_last_success_timestamp_seconds",
            "When each worker task last succeeded (Unix time).",
            ("task",),
        )
        for name, when in last.items():
            success.labels(str(name)).set(float(when))
        up.labels("redis").set(1)
    except Exception:
        up.labels("redis").set(0)
    finally:
        await client.aclose()
    return generate_latest(registry)


def install_metrics(app: FastAPI, settings: Settings, internal_hosts: tuple[str, ...]) -> None:
    http = HttpMetrics()

    @app.middleware("http")
    async def measure(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path == METRICS_PATH:
            return await call_next(request)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            http.observe(request.method, route_of(request), status, time.perf_counter() - started)

    @app.get(METRICS_PATH, include_in_schema=False)
    async def metrics(request: Request) -> Response:
        if (request.url.hostname or "") not in internal_hosts:
            return Response(status_code=404)
        body = generate_latest(http.registry) + await live_metrics(settings)
        return Response(body, media_type=CONTENT_TYPE_LATEST)
