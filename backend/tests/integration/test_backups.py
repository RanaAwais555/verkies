"""Slice 7.2: what the backup service recorded, for admins and Prometheus."""

from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from tests.integration.conftest import ApiClient, make_user

pytestmark = pytest.mark.integration


def run(
    engine: Engine, kind: str, status: str, hours_ago: float, detail: str | None = None
) -> None:
    # As ops/backup/backup.sh writes it, with psql: the database supplies the id.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO backup_runs (kind, status, started_at, finished_at, bytes, detail)"
                " VALUES (:k, :s, now() - make_interval(secs => :h * 3600 + 5),"
                " now() - make_interval(secs => :h * 3600), 1024, :d)"
            ),
            {"k": kind, "s": status, "h": hours_ago, "d": detail},
        )


def test_backup_status_shows_the_latest_run_and_last_success(
    engine: Engine, api: ApiClient, make_api: Callable[[], ApiClient]
) -> None:
    make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    assert [(b["kind"], b["latest"]) for b in api.get("/system/backups").json()] == [
        ("dump", None),
        ("documents", None),
        ("offsite", None),
        ("drill", None),
    ]

    run(engine, "dump", "ok", 30)
    run(engine, "dump", "ok", 6, "vros-new.dump")
    run(engine, "offsite", "ok", 30)
    run(engine, "offsite", "failed", 6, "Upload to offsite:vros failed or did not verify")
    run(engine, "drill", "ok", 50, "restored 73 tables at schema 0029")
    by_kind = {b["kind"]: b for b in api.get("/system/backups").json()}
    assert by_kind["dump"]["label"] == "Database dump"
    assert by_kind["dump"]["latest"]["detail"] == "vros-new.dump"
    assert by_kind["dump"]["latest"]["bytes"] == 1024
    offsite = by_kind["offsite"]
    assert offsite["latest"]["status"] == "failed"
    assert offsite["last_ok"]["status"] == "ok"
    assert offsite["last_ok"]["finished_at"] < offsite["latest"]["finished_at"]
    assert by_kind["documents"]["latest"] is None

    metrics = api.http.get("/metrics", headers={"host": "localhost"}).text
    assert 'vros_backup_last_success_timestamp_seconds{kind="dump"}' in metrics
    assert 'vros_backup_last_failed{kind="offsite"} 1.0' in metrics
    assert 'vros_backup_last_failed{kind="dump"} 0.0' in metrics
    assert 'kind="documents"' not in metrics  # never ran: no value, never a made-up zero

    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    assert seller.get("/system/backups").status_code == 403


def test_the_database_refuses_unknown_kinds_and_statuses(engine: Engine) -> None:
    with pytest.raises(Exception, match="ck_backup_runs_kind"):
        run(engine, "snapshot", "ok", 1)
    with pytest.raises(Exception, match="ck_backup_runs_status"):
        run(engine, "dump", "maybe", 1)
