"""Rate limits (SECURITY.md §4; slice 7.3).

A fixed window per limit and key, counted in Redis so every API process shares it. Sign-in and
invite links are limited per client address (password spraying, token guessing); password
changes, research and the API as a whole per person. The per-account lockout (SECURITY.md §1)
still applies on top.

If Redis cannot be reached the request is allowed and a warning logged: a broken cache must not
lock the team out. The client address is the one Caddy saw (uvicorn trusts its X-Forwarded-For;
FORWARDED_ALLOW_IPS in docker-compose.yml).
"""

import logging
import math
import time
from dataclasses import dataclass

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.config import Settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

KEY_PREFIX = "vros:rl"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, retry_after: int) -> None:
        minutes = max(1, math.ceil(retry_after / 60))
        super().__init__(
            f"Too many attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            details={"retry_after": retry_after},
        )
        self.headers = {"Retry-After": str(retry_after)}


@dataclass(frozen=True)
class Limit:
    name: str
    limit: int
    window_seconds: int


def limits(settings: Settings) -> dict[str, Limit]:
    return {
        "login": Limit("login", settings.rate_limit_login_per_ip, 600),
        "invite": Limit("invite", settings.rate_limit_invite_per_ip, 600),
        "password": Limit("password", settings.rate_limit_password_changes_per_hour, 3600),
        "research": Limit("research", settings.rate_limit_research_per_hour, 3600),
        "api": Limit("api", settings.rate_limit_api_per_minute, 60),
    }


async def hit(settings: Settings, name: str, key: str) -> None:
    """Count one request against a limit; raise RateLimited once it is used up."""
    if not settings.rate_limits_enabled:
        return
    limit = limits(settings)[name]
    now = time.time()
    window = int(now // limit.window_seconds)
    bucket = f"{KEY_PREFIX}:{limit.name}:{key}:{window}"
    client = aioredis.from_url(settings.redis_url)
    try:
        pipe = client.pipeline()
        pipe.incr(bucket)
        pipe.expire(bucket, limit.window_seconds)
        count, _ = await pipe.execute()
    except RedisError:
        logger.warning("rate limit not checked: Redis unavailable", extra={"limit": name})
        return
    finally:
        await client.aclose()
    if int(count) > limit.limit:
        retry_after = max(1, math.ceil((window + 1) * limit.window_seconds - now))
        logger.warning("rate limited", extra={"limit": name})
        raise RateLimited(retry_after)
