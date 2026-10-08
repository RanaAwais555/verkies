"""Liveness and readiness endpoints.

Liveness says the process is up. Readiness checks every dependency the API needs and
returns 503 if any is down, so Compose and load balancers only route to a working API.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.config import Settings, get_settings
from app.db import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

HealthCheck = Callable[[], Awaitable[None]]


class CheckResult(BaseModel):
    status: Literal["ok", "down"]
    error: str | None = None


class LiveResponse(BaseModel):
    status: Literal["ok"]
    version: str


class ReadyResponse(BaseModel):
    status: Literal["ok", "down"]
    checks: dict[str, CheckResult]


async def check_database() -> None:
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))


async def check_redis() -> None:
    client = aioredis.from_url(get_settings().redis_url)
    try:
        await client.ping()
    finally:
        await client.aclose()


def get_health_checks() -> dict[str, HealthCheck]:
    return {"database": check_database, "redis": check_redis}


async def _run(name: str, check: HealthCheck, timeout: float) -> CheckResult:
    try:
        await asyncio.wait_for(check(), timeout=timeout)
    except TimeoutError:
        logger.warning("health check timed out", extra={"check": name})
        return CheckResult(status="down", error="timeout")
    except Exception as exc:
        logger.warning("health check failed", extra={"check": name, "error": repr(exc)})
        # Error class only: connection strings and hostnames stay in the logs.
        return CheckResult(status="down", error=type(exc).__name__)
    return CheckResult(status="ok")


@router.get("/live")
async def live(settings: Annotated[Settings, Depends(get_settings)]) -> LiveResponse:
    return LiveResponse(status="ok", version=settings.app_version)


@router.get("/ready", responses={503: {"model": ReadyResponse}})
async def ready(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    checks: Annotated[dict[str, HealthCheck], Depends(get_health_checks)],
) -> ReadyResponse:
    names = list(checks)
    results = await asyncio.gather(
        *(_run(name, checks[name], settings.health_check_timeout) for name in names)
    )
    by_name = dict(zip(names, results, strict=True))
    overall: Literal["ok", "down"] = "ok" if all(r.status == "ok" for r in results) else "down"
    if overall == "down":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status=overall, checks=by_name)
