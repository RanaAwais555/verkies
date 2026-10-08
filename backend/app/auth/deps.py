"""FastAPI dependencies: current session and user, permission checks, CSRF.

Cookies: the session cookie is HttpOnly; the CSRF cookie is readable by the frontend, which
echoes it in the X-CSRF-Token header on every state-changing request (double submit). With
HTTPS the cookies use the __Host- prefix, so no subdomain can set or overwrite them.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.models import User, UserSession
from app.auth.tokens import new_token, tokens_match
from app.config import Settings, get_settings
from app.core.errors import NotAuthenticated, PermissionDenied
from app.db import get_session

CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

DbSession = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def cookie_names(settings: Settings) -> tuple[str, str]:
    prefix = "__Host-" if settings.secure_cookies else ""
    return f"{prefix}vros_session", f"{prefix}vros_csrf"


def set_auth_cookies(response: Response, token: str, settings: Settings) -> str:
    session_name, csrf_name = cookie_names(settings)
    max_age = settings.session_max_days * 24 * 3600
    csrf = new_token()
    common = {"max_age": max_age, "path": "/", "secure": settings.secure_cookies, "samesite": "lax"}
    response.set_cookie(session_name, token, httponly=True, **common)  # type: ignore[arg-type]
    response.set_cookie(csrf_name, csrf, httponly=False, **common)  # type: ignore[arg-type]
    return csrf


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    for name in cookie_names(settings):
        response.delete_cookie(name, path="/", secure=settings.secure_cookies, samesite="lax")


async def current_session(request: Request, db: DbSession, settings: AppSettings) -> UserSession:
    session_name, csrf_name = cookie_names(settings)
    token = request.cookies.get(session_name)
    if not token:
        raise NotAuthenticated("Sign in to continue.")
    session = await service.resolve_session(db, token, settings=settings)
    if session is None:
        raise NotAuthenticated("Your session has ended. Sign in again.")
    if request.method not in SAFE_METHODS:
        cookie = request.cookies.get(csrf_name, "")
        header = request.headers.get(CSRF_HEADER, "")
        if not cookie or not header or not tokens_match(cookie, header):
            raise PermissionDenied("Missing or invalid CSRF token.", code="csrf_failed")
    return session


CurrentSession = Annotated[UserSession, Depends(current_session)]


async def current_user(session: CurrentSession) -> User:
    return session.user


CurrentUser = Annotated[User, Depends(current_user)]


def require_permission(*keys: str) -> Callable[[User], Awaitable[User]]:
    """Allow the request if the user holds any of the given permissions."""

    async def check(user: CurrentUser) -> User:
        if not user.permission_keys.intersection(keys):
            raise PermissionDenied("You do not have permission to do this.")
        return user

    return check
