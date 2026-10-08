# syntax=docker/dockerfile:1
# Two targets: `api` (slim) and `worker` (adds headless Chromium for JavaScript rendering).
FROM python:3.13-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first so code changes don't invalidate the dependency layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 --no-create-home vros \
    && mkdir -p /data/storage && chown vros /data/storage
ENV VROS_STORAGE_DIR=/data/storage
USER vros

EXPOSE 8000

# Behind Caddy: trust X-Forwarded-* from the proxy. The API port is never published in
# production, so only Caddy can reach it.
ENV FORWARDED_ALLOW_IPS="*"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

FROM api AS worker
USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN uv sync --frozen --no-dev --extra render
# Headless shell only, with its system libraries. Installed as root, readable by vros.
RUN playwright install --with-deps --only-shell chromium && chmod -R a+rX /ms-playwright
USER vros
CMD ["celery", "-A", "app.workers.celery_app:celery_app", "worker", "--loglevel=INFO", "--concurrency=2"]
