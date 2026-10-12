"""Refuse passwords that have appeared in data breaches (SECURITY.md §1; slice 7.3).

Uses the Pwned Passwords range API by k-anonymity: only the first 5 characters of the
password's SHA-1 hash are sent, the service answers with every breached hash sharing them
(padded with decoys), and the match is made here. Neither the password nor its full hash leaves
the server. Switched off with VROS_BREACHED_PASSWORD_CHECK=false. If the service cannot be
reached the password is accepted and a warning logged: an outside outage must not stop people
signing up or changing a password.
"""

import hashlib
import logging

import httpx

from app.config import get_settings
from app.core.errors import ValidationFailed

logger = logging.getLogger(__name__)

RANGE_URL = "https://api.pwnedpasswords.com/range/"
TIMEOUT = 3.0
# Tests replace this with a fake; None means the real network.
transport: httpx.AsyncBaseTransport | None = None


async def times_breached(password: str) -> int | None:
    """How many times the password appears in known breaches, or None if unknown."""
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            transport=transport,
            timeout=TIMEOUT,
            headers={"Add-Padding": "true", "User-Agent": settings.crawler_user_agent},
        ) as client:
            response = await client.get(RANGE_URL + prefix)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("breached-password check unavailable", extra={"error": type(exc).__name__})
        return None
    for line in response.text.splitlines():
        candidate, _, count = line.strip().partition(":")
        if candidate == suffix:
            return int(count or 0)
    return 0


async def check_not_breached(password: str) -> None:
    if not get_settings().breached_password_check:
        return
    count = await times_breached(password)
    if count:
        raise ValidationFailed(
            f"This password has appeared {count:,} time{'s' if count != 1 else ''} in known "
            "data breaches, so attackers try it. Choose a different one."
        )
