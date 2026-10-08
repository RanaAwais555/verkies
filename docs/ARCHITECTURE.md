# VROS Architecture

Source of truth for product intent: `VROS_Master_Context.md`. This document covers how it is built. Section references (§n) point to the master context.

## 1. Shape

A modular monolith. One deployable backend, one worker, one frontend. Modules are separated by package boundaries and typed interfaces so any of them can be extracted later, but nothing is split into services up front.

```
                ┌──────────────┐
                │  Next.js UI  │  TypeScript, Tailwind
                └──────┬───────┘
                       │ REST/JSON (OpenAPI)
                ┌──────▼───────┐        ┌────────────┐
                │ FastAPI app  │───────▶│ PostgreSQL │  pgvector, pg_trgm
                │  (api layer) │        └─────▲──────┘
                └──────┬───────┘              │
                       │ enqueue              │
                ┌──────▼───────┐        ┌─────┴──────┐
                │    Redis     │◀──────▶│Celery worker│  crawl, analyse, score
                └──────────────┘        └─────┬──────┘
                                              │ via provider interfaces
              ┌───────────────┬───────────────┼───────────────┬──────────────┐
              ▼               ▼               ▼               ▼              ▼
         Fetcher         AI provider      Search          Storage         Email/Cal
      (httpx/Playwright)  (Ollama)      (SearXNG/CSV)   (local fs)       (later)
```

## 2. Repository layout

```
verkies/
├── backend/
│   ├── pyproject.toml
│   ├── alembic/                    # migrations
│   ├── app/
│   │   ├── main.py                 # FastAPI factory
│   │   ├── config.py               # typed settings (env)
│   │   ├── db.py                   # engine, session
│   │   ├── core/                   # ids, clock, errors, logging, pagination
│   │   ├── auth/                   # users, roles, sessions, RBAC deps
│   │   ├── audit/                  # audit log writer
│   │   ├── accounts/               # Account (central entity), contacts
│   │   ├── crm/                    # leads, opportunities, tasks, activities, timeline
│   │   ├── evidence/               # Evidence model, validation, claim classes
│   │   ├── research/               # research runs, job state, orchestration
│   │   ├── intelligence/           # analysers: website, seo, conversion, product, tech
│   │   ├── opportunities/          # opportunity detectors (rules) + catalogue
│   │   ├── qualification/          # ICP, negative ICP, rejection reasons
│   │   ├── scoring/                # ten scores, priority score, bands, config
│   │   ├── briefs/                 # lead brief assembly, Why Verkies / Why Now
│   │   ├── similarity/             # reference projects, similarity score
│   │   ├── providers/              # interfaces + implementations (see §4)
│   │   └── workers/                # Celery app, tasks
│   └── tests/{unit,integration,e2e}
├── frontend/                       # Next.js app router
├── docs/
├── docker-compose.yml
└── .github/workflows/ci.yml
```

Rules:

- A module exposes a small service API (`service.py`) and Pydantic schemas. Other modules call the service, never another module's tables directly, except through the `accounts` foreign keys.
- Routers hold no business logic. Services hold no HTTP concerns.
- No file over roughly 400 lines. No scoring weights, thresholds, provider names or magic values in code; they live in config tables or settings.

## 3. Account-centric core (§6)

`accounts` is the permanent entity. Leads, opportunities, deals, projects, tasks, activities, evidence, contacts and research runs all carry `account_id`. Lifecycle changes update `accounts.lifecycle_state` and append to the timeline; no record is moved or copied when a company converts. Details in `DATA_MODEL.md`.

## 4. Provider abstraction (§18)

Business logic depends on interfaces in `app/providers/base.py`. Implementations are chosen by settings. A missing or failing provider never takes the app down; callers receive a typed `ProviderUnavailable` and degrade.

| Interface | Phase 1 implementation | Later |
| --- | --- | --- |
| `Fetcher` | `HttpxFetcher`, `PlaywrightFetcher` | caching proxy |
| `AIProvider` | `OllamaProvider`, `NullProvider` (no AI, deterministic text only) | hosted models |
| `Storage` | `LocalStorage` | MinIO |
| `SearchProvider` | `CsvImportProvider` | `SearxngProvider`, Companies House bulk |
| `CompanyDataProvider` | none | Companies House, SEC EDGAR, Wikidata |
| `EmailProvider`, `CalendarProvider` | none | Gmail, Graph, SMTP/IMAP |
| `EmbeddingProvider` | `OllamaEmbeddings`, `NullEmbeddings` | |

Tests use fakes for every interface. No test touches the network.

## 5. Research pipeline (Phase 1)

Implemented so far: all eight stages (validate, crawl, extract, detect, qualify, score, match, brief) with the run API (`/api/v1/research-runs`: start, list, detail with stages and pages, intelligence, assessment, brief, cancel, retry) and versioned configuration (`/api/v1/config/{icp,scoring}`). Extraction is described in `OBSERVATIONS.md`. The worker image (`backend/Dockerfile` target `worker`) adds headless Chromium; the API image does not. Fetched bodies live in the `storage` volume.


A research run is one Celery job with ordered stages. Each stage writes its own progress row, so the UI shows crawl progress (§20).

1. **Validate URL.** Scheme allowlist, resolve DNS, reject private/loopback/link-local/metadata addresses (SECURITY.md §3).
2. **Crawl.** robots.txt, sitemap, then homepage plus a bounded set of high-value pages (about, team, services, contact, pricing, careers, login/signup, blog). Static fetch first; Playwright only if the static page has too little content. Bounded by page count, bytes, redirects, per-domain concurrency and timeouts.
3. **Extract observations.** Pure functions turn pages into typed observations (title, forms, CTAs, tech fingerprints, headers, team names, job links, and so on). Each observation becomes an `evidence` row with source URL, collected time, text and type.
4. **Detect opportunities.** Rule detectors map observations to opportunity candidates; each candidate lists the evidence IDs behind it (§9).
5. **Qualify.** ICP fit, negative ICP and rejection reasons (ICP_SPEC.md).
6. **Score.** Ten dimensions and the priority score (SCORING_SPEC.md).
7. **Match.** Service matching (max three) and reference-project similarity.
8. **Brief.** Assemble the lead brief. If an AI provider is available, it writes the prose from the evidence set only; otherwise a deterministic template is used (AI_SPEC.md).
9. **Await review.** Run ends `completed`; the prospect sits in a review queue until a person approves or rejects.

Approve creates or updates the `Account` (matched by normalised domain), creates a `Lead`, an `Opportunity` where one was detected, a `Task` (the next action, with owner and due date) and timeline entries, in one transaction. Reject stores the rejection reason and keeps the record searchable and out of the sales queue.

**Implemented (slice 1.6):** `backend/app/prospects/` (queue, approve, reject), `backend/app/accounts/` (list, Account 360), `backend/app/crm/` (tasks, timeline, "requires attention").

- `GET /api/v1/prospects` is the review queue: completed, undecided runs with a current brief, qualifying prospects first, then by priority, each with the engines' recommendation and any possible duplicates.
- `POST /api/v1/prospects/{run_id}/approve` locks the run row and, in one transaction:
  - creates the Account, or reuses it when the domain is already known;
  - attaches the run's evidence, observations, claims and score snapshot to the Account (`account_id` set once, as the append-only triggers allow);
  - creates the Lead (with its score snapshot), an Opportunity from the strongest detected problem with the primary matched service, Contacts for people named on the site, and the next-action Task;
  - writes the timeline and the audit entries.
- Approval refuses (409) when:
  - the domain is suppressed (`suppressed`);
  - the domain belongs to another account than the one chosen (`domain_taken`);
  - similarly named accounts exist and the reviewer has not chosen one (`account_id`) or confirmed a new company (`create_new_account`) (`possible_duplicate`, with the candidates in `error.details`).
- Approving against the engines (hard reject or below the threshold) needs an `override_reason` of at least 10 characters, stored on the audit entry.
- A unique index on `leads.research_run_id` makes a double approval impossible.
- `POST /api/v1/prospects/{run_id}/reject` stores the reason and note on the run. It can add the domain to the suppression list, adds a timeline event if the domain belongs to an existing account, and is audited. Rejected runs leave the queue and stay searchable with `GET /api/v1/research-runs?review_status=rejected&q=<domain>`.
- `GET /api/v1/accounts` (search by name or any domain, filter by type and owner) and `GET /api/v1/accounts/{id}` (Account 360: overview, all ten scores with Unknown as null, domains, leads, opportunities with attention reasons, contacts, tasks, research runs, latest brief), `/timeline` and `/audit` (needs `audit.read`).
- `GET /api/v1/tasks` (yours and open by default), `PATCH /api/v1/tasks/{id}` (title, owner, due date), `POST /api/v1/tasks/{id}/complete`, and `GET /api/v1/opportunities/requires-attention`. An opportunity requires attention when its next action is missing, closed, unowned or undated.
- UUIDv7 IDs are strictly increasing within a process, so events written in one transaction keep their order on the timeline.

Job statuses: Queued, Running, Completed, Failed, Cancelled, Retrying. Every job stores start, finish, progress, error and retry state (§18).

## 6. API

REST under `/api/v1`, OpenAPI generated by FastAPI, typed client generated for the frontend. Cursor pagination for lists. Errors use one problem-details shape. Mutating endpoints write audit entries.

Phase 1 endpoint groups: `auth`, `users`, `research-runs`, `prospects`, `accounts` (with timeline and audit), `tasks`, `opportunities`, `config` (ICP and scoring), `catalogue` (services, reference projects; slice 1.7), `audit`. Errors are `{"error": {"code", "message", "details?"}}`.

## 7. Frontend

Next.js app router, TypeScript, Tailwind. Phase 1 screens: login; Home ("What should I do today?"); New research (URL entry) with live progress; Lead brief review (card with Approve / Reject); Accounts list; Account 360 with Overview, Intelligence, Leads, Tasks, Timeline and Audit tabs; Settings (ICP, scoring weights, service catalogue, reference projects). Fact, Inference and Recommendation are visually distinct everywhere they appear.

## 8. Cross-cutting

- **Config:** `pydantic-settings`, environment only, no secrets in the repo.
- **Logging:** structured JSON with request ID and run ID.
- **Migrations:** Alembic, one migration per change, reviewed with the model.
- **Soft delete:** `deleted_at` on user-facing entities; evidence and audit rows are append-only.
- **Caching:** raw HTTP responses stored with fetch time and reused until stale (§18A: 30 days for company facts, daily for jobs and news; website crawl default 7 days, user can force refresh).
- **Time:** all timestamps UTC `timestamptz`.
- **IDs:** UUIDv7 primary keys.

## 9. Deployment (team use, live domain)

VROS is a multi-user team system, built from the start to run on a live domain.

**Single origin.** One public hostname (e.g. `vros.verkies.co`). A Caddy reverse proxy terminates TLS (automatic Let's Encrypt certificates) and routes `/api/*` to the API and everything else to the frontend. The browser only ever talks to one origin, so session cookies are first-party, `SameSite=Lax` works and no CORS is needed in production.

```
Internet ──443──▶ Caddy ──/api/*──▶ api:8000 ──▶ postgres, redis
                    └──── /* ─────▶ frontend:3000
                                    worker ──▶ postgres, redis, outbound web
```

**Compose files.**

| File | Use |
| --- | --- |
| `docker-compose.yml` | Base services: `postgres` (pgvector), `redis`, `migrate` (applies Alembic migrations and exits; `api` and `worker` start only if it succeeds), `api`, `worker`, `frontend`, `caddy`. Development defaults; database and Redis ports published on localhost only |
| `docker-compose.prod.yml` | Production overlay: adds `caddy` and `backup`; no database or Redis ports published; `restart: unless-stopped`; all secrets from `.env` |

Development: `docker compose up`. Production: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` on one VPS with the domain's DNS `A` record pointing at it.

**Production configuration fails closed.** With `VROS_ENVIRONMENT=production` the API refuses to start unless `VROS_SECRET_KEY` is set (≥ 32 characters), `VROS_PUBLIC_URL` is `https://`, and the database password is not the development default. OpenAPI docs are off, and only the public hostname is accepted as `Host`.

**Backups.** The `backup` service runs a nightly `pg_dump` into a volume and keeps 14 days. Off-site copies and restore drills are Phase 7.

**Ollama** runs on the host or an optional Compose profile; the worker reaches it over the internal network.

## 10. Quality gates

CI runs lint (ruff), type check (mypy/pyright), backend tests, frontend lint and type check, and the end-to-end test. Pull requests that change scoring or ICP behaviour must update the matching spec document.
