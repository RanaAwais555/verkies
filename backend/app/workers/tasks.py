"""Worker tasks. Research-pipeline tasks arrive in slice 1.2."""

from app.workers.celery_app import celery_app


@celery_app.task(name="vros.ping")
def ping() -> str:
    """Round-trip check that a worker is consuming the queue."""
    return "pong"
