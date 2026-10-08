from app.workers.celery_app import celery_app
from app.workers.tasks import ping


def test_ping_task_is_registered_and_returns_pong() -> None:
    assert "vros.ping" in celery_app.tasks
    assert ping.apply().get() == "pong"


def test_worker_acknowledges_late_so_crashed_jobs_are_retried() -> None:
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True


def test_worker_process_registers_every_table() -> None:
    """The worker imports only what its tasks need. Run that import in a fresh interpreter, as
    production does, and check every table is known (a missing one breaks foreign keys)."""
    import subprocess
    import sys

    import app.models
    from app.core.models import Base

    assert "users" in app.models.Base.metadata.tables

    script = (
        "import app.workers.tasks\n"
        "from app.core.models import Base\n"
        "print(len(Base.metadata.tables))\n"
    )
    out = subprocess.run(  # noqa: S603 - fixed script, our own interpreter
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert int(out.stdout.strip().splitlines()[-1]) == len(Base.metadata.tables)
