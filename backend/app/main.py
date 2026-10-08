"""FastAPI application factory."""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.audit.router import router as audit_router
from app.auth.admin_router import router as users_router
from app.auth.router import router as auth_router
from app.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, request_id_var
from app.health.router import router as health_router
from app.research.router import router as research_router

API_PREFIX = "/api/v1"
REQUEST_ID_HEADER = "X-Request-ID"
# Loopback and the Compose service name: reachable only inside the Docker network.
INTERNAL_HOSTS = ("localhost", "api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    docs = settings.docs_enabled
    app = FastAPI(
        title="Verkies Revenue Operating System",
        version=settings.app_version,
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
    )
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    if settings.is_production:
        # Reject requests addressed to any other hostname (Host-header attacks). Internal
        # names stay allowed: the container healthcheck (localhost) and the frontend's
        # server-side calls (api) never pass through Caddy.
        app.add_middleware(
            TrustedHostMiddleware, allowed_hosts=[settings.public_host, *INTERNAL_HOSTS]
        )

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Accept a caller's ID only if it is short and printable; otherwise mint one.
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        rid = incoming if 0 < len(incoming) <= 64 and incoming.isprintable() else uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response

    install_error_handlers(app)
    for router in (health_router, auth_router, users_router, audit_router, research_router):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
