from app.workers.celery_app import celery_app
from app.workers.tasks import ping


def test_ping_task_is_registered_and_returns_pong() -> None:
    assert "vros.ping" in celery_app.tasks
    assert ping.apply().get() == "pong"


def test_worker_acknowledges_late_so_crashed_jobs_are_retried() -> None:
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
