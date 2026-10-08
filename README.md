# Verkies Revenue Operating System (VROS)

An intelligence-first revenue platform for Verkies Private Limited: prospect intelligence, qualification, CRM, client lifecycle and learning around a permanent Account.

**Status:** specification complete, Phase 1 (vertical slice) not yet started.

## Read first

| Document | Purpose |
| --- | --- |
| [`docs/VROS_Master_Context.md`](docs/VROS_Master_Context.md) | Source of truth for the product (v1.1) |
| [`docs/VERKIES_PROFILE.md`](docs/VERKIES_PROFILE.md) | Verkies' own services and reference projects, from verkies.co (seed data, unconfirmed) |
| [`docs/GAP_ANALYSIS.md`](docs/GAP_ANALYSIS.md) | Repo vs. master context, risks, open decisions |
| [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) | Phase 1 scope, rules, acceptance mapping |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design and repository layout |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | PostgreSQL schema, Account-centric |
| [`docs/ICP_SPEC.md`](docs/ICP_SPEC.md) | ICP and negative-ICP engine |
| [`docs/SCORING_SPEC.md`](docs/SCORING_SPEC.md) | Ten scores, priority score, gates, bands |
| [`docs/AI_SPEC.md`](docs/AI_SPEC.md) | Grounding rules, models, degradation |
| [`docs/PROVIDER_SPEC.md`](docs/PROVIDER_SPEC.md) | Provider interfaces and free data sources |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Auth, RBAC, SSRF, audit, compliance |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phases and Phase 1 slices |

## Stack

Next.js · TypeScript · Tailwind · FastAPI · PostgreSQL (pgvector, pg_trgm) · Redis · Celery · Playwright · Ollama · Docker Compose. Free and open source; no paid service is required.
