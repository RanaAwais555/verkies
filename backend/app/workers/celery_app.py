"""Celery app. Long-running work (crawls, analysis, scoring) runs here, never in a request."""

from celery import Celery

import app.models  # noqa: F401 - the worker must know every table (foreign keys span modules)
from app.config import get_settings


def create_celery() -> Celery:
    settings = get_settings()
    celery = Celery("vros", broker=settings.redis_url, backend=settings.redis_url)
    celery.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )
    celery.autodiscover_tasks(["app.workers"])
    return celery


celery_app = create_celery()
