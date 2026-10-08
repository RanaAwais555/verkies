# Verkies Revenue Operating System (VROS)

An intelligence-first revenue platform for Verkies Private Limited: prospect intelligence, qualification, CRM, client lifecycle and learning around a permanent Account. Built for team use, deployable to a live domain.

**Status:** Phase 1, slice 1.0 (foundation) done. Next: 1.1 schema, team auth and audit. See [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Run it locally

Everything in Docker (needs Docker with Compose v2.24+):

```bash
docker compose up --build
# open http://localhost:8080        (app, through Caddy, same routing as production)
#      http://localhost:8000/api/v1/docs   (API docs, development only)
```

Or run the parts directly (needs PostgreSQL 16 and Redis 7 on localhost, user/password/db `vros`):

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload          # API on :8000
cd backend && uv run celery -A app.workers.celery_app:celery_app worker  # worker
cd frontend && npm install && npm run dev                                # UI on :3000, proxies /api
```

## Checks

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
cd backend  && VROS_RUN_INTEGRATION=1 uv run pytest tests/integration    # needs Postgres + Redis
cd frontend && npm run lint && npm run typecheck && npm run build
```

CI runs all of these plus Compose and Caddyfile validation and image builds (`.github/workflows/ci.yml`).

## Deploy to a live domain

One small VPS (2 vCPU / 4 GB is enough for the team stack without local AI) with Docker installed.

1. Point the domain's DNS `A` (and `AAAA` if any) record, e.g. `vros.verkies.co`, at the server. Open ports 80 and 443.
2. Clone the repo on the server and create the config: `cp .env.example .env`, then fill every REQUIRED value. Generate secrets with `openssl rand -hex 32` (secret key) and `openssl rand -hex 24` (database password).
3. Start it:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
   Caddy obtains the TLS certificate automatically on first request.
4. Check `https://<your-domain>/api/v1/health/ready` returns `"status":"ok"`.

Production fails closed: the deploy stops if a required value is missing, and the API refuses to start with a short secret key, a non-HTTPS URL or the development database password. Only Caddy (80/443) is exposed; the database, Redis and API are reachable only inside the Docker network. Nightly database dumps go to the `backups` volume (14 days kept); copy them off the server.

Team accounts are invite-only (no public sign-up). The first admin is created from the server's command line; this arrives in slice 1.1.

To update: `git pull` then rerun the `up -d --build` command.

## Documents

| Document | Purpose |
| --- | --- |
| [`docs/VROS_Master_Context.md`](docs/VROS_Master_Context.md) | Source of truth for the product (v1.1) |
| [`docs/VERKIES_PROFILE.md`](docs/VERKIES_PROFILE.md) | Verkies' services and reference projects (seed data) |
| [`docs/GAP_ANALYSIS.md`](docs/GAP_ANALYSIS.md) | Repo vs. master context, risks, open decisions |
| [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) | Phase 1 scope, rules, acceptance mapping |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design, repository layout, deployment |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | PostgreSQL schema, Account-centric |
| [`docs/ICP_SPEC.md`](docs/ICP_SPEC.md) | ICP and negative-ICP engine |
| [`docs/SCORING_SPEC.md`](docs/SCORING_SPEC.md) | Ten scores, priority score, gates, bands |
| [`docs/AI_SPEC.md`](docs/AI_SPEC.md) | Grounding rules, models, degradation |
| [`docs/PROVIDER_SPEC.md`](docs/PROVIDER_SPEC.md) | Provider interfaces and free data sources |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Auth, RBAC, SSRF, audit, compliance |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phases and Phase 1 slices |

## Stack

Next.js · TypeScript · Tailwind · FastAPI · PostgreSQL (pgvector, pg_trgm) · Redis · Celery · Caddy · Docker Compose. Free and open source; no paid service is required.
