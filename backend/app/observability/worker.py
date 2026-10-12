"""What the worker did, kept in Redis so the API can expose it (slice 7.1).

The worker runs in its own process (several, with prefork), so its counters cannot live in the
API's memory. Each task's outcome is added to a Redis hash; the API reads it when Prometheus
scrapes /metrics. Recording never fails a task: a Redis error is logged and ignored.
"""

import logging
import time
from typing import Any

import redis
from celery.signals import task_failure, task_postrun, task_prerun, task_retry

from app.config import get_settings

logger = logging.getLogger(__name__)

TASKS_KEY = "vros:metrics:tasks"  # "<task>|<state>" -> count, "<task>|seconds" -> total
LAST_SUCCESS_KEY = "vros:metrics:last_success"  # task -> unix time of its last success
_started: dict[str, float] = {}
_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(get_settings().redis_url)
    return _client


def record(task: str, state: str, seconds: float | None = None) -> None:
    try:
        pipe = _redis().pipeline()
        pipe.hincrby(TASKS_KEY, f"{task}|{state}", 1)
        if seconds is not None:
            pipe.hincrbyfloat(TASKS_KEY, f"{task}|seconds", seconds)
        if state == "success":
            pipe.hset(LAST_SUCCESS_KEY, task, time.time())
        pipe.execute()
    except redis.RedisError:
        logger.warning("could not record task metrics", extra={"task": task, "state": state})


def _prerun(task_id: str | None = None, **_: Any) -> None:
    if task_id:
        _started[task_id] = time.monotonic()


def _postrun(
    task_id: str | None = None, task: Any = None, state: str | None = None, **_: Any
) -> None:
    started = _started.pop(task_id or "", None)
    seconds = time.monotonic() - started if started is not None else None
    name = getattr(task, "name", "unknown")
    # Failures and retries are counted by their own signals; postrun adds the duration.
    if state == "SUCCESS":
        record(name, "success", seconds)
    elif seconds is not None:
        try:
            _redis().hincrbyfloat(TASKS_KEY, f"{name}|seconds", seconds)
        except redis.RedisError:
            logger.warning("could not record task duration", extra={"task": name})


def _failure(sender: Any = None, **_: Any) -> None:
    record(getattr(sender, "name", "unknown"), "failure")


def _retry(sender: Any = None, **_: Any) -> None:
    record(getattr(sender, "name", "unknown"), "retry")


# weak=False: the handlers are module functions that must stay connected.
task_prerun.connect(_prerun, weak=False)
task_postrun.connect(_postrun, weak=False)
task_failure.connect(_failure, weak=False)
task_retry.connect(_retry, weak=False)
