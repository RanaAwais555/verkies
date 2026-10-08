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
- `GET /api/v1/tasks` (yours and open by default), `POST /api/v1/tasks` (on an account; given an opportunity it becomes that opportunity's next action), `PATCH /api/v1/tasks/{id}` (title, owner, due date), `POST /api/v1/tasks/{id}/complete`, and `GET /api/v1/opportunities/requires-attention`. An opportunity requires attention when its next action is missing, closed, unowned or undated.
- UUIDv7 IDs are strictly increasing within a process, so events written in one transaction keep their order on the timeline.

Job statuses: Queued, Running, Completed, Failed, Cancelled, Retrying. Every job stores start, finish, progress, error and retry state (§18).

## 5a. Discovery (Phase 2)

**CSV import (slice 2.1):** `backend/app/discovery/`.
- **Upload:** `POST /api/v1/discovery/imports` takes the file's text, read in the browser.
  - Limits: 2 MB, 5,000 rows, 50 columns, 2,000 characters per cell.
  - The delimiter (`,` `;` tab `|`) is taken from the header row. Every row is stored as uploaded, and the columns are mapped from header names where they are clear.
- **Mapping and checking:** `PUT …/{id}/mapping` applies a mapping (website required; name, country, industry, notes optional) and sorts every row into exactly one status:
  - new;
  - invalid (with the reason);
  - duplicate in the file;
  - existing account (the domain belongs to one);
  - already researched (with the run);
  - possible duplicate (name similarity ≥ 0.6 to an account);
  - suppressed.

  Rows already sent to research keep their status.
- **Research:** `POST …/{id}/research` starts research on up to 50 chosen rows (only new or possible-duplicate ones) through the normal research flow. A person still approves or rejects each one. Nothing becomes an Account here.
- **History:** `GET /api/v1/discovery/imports` lists past imports, visible to their creator and to `accounts.read`.

**Export:** `GET /api/v1/accounts/export?format=csv|json` returns the accounts the user may see. Cells that a spreadsheet would read as a formula are prefixed with `'`, and every export is audited.

**Buying signals (slice 2.2):** `backend/app/signals/`.
- **The stage:** a `signals` stage runs after `extract`. It reads the job-board link (`hiring.job_board`) and feed links (`company.feed`) the site itself published, then:
  - queries the board's public JSON API (Greenhouse, Lever, Ashby, Workable; the board token is validated);
  - fetches the company's RSS/Atom feeds under its robots.txt. Feeds with a DOCTYPE or entities are refused.
- **Storage:** each signal is an observation in the `signals` area with dated evidence (`evidence.published_at`).
- **Classification:** signal types and strengths follow master context §9 (`app/signals/classify.py`).
- **Use:** signals drive Intent and Timing (SCORING_SPEC.md §2) and add dated "Why now" facts to the brief.
- **Not used:** news-search feeds that match on company name (for example Google News) are not used. A name match is not evidence that the item is about this company.

**Company registries (slice 2.3):** `backend/app/registry/`.
- **The stage:** an `enrich` stage runs after `signals`. It looks up Wikidata by the company's official website, then Companies House by the registered number printed on the site (or held by Wikidata).
- **Name check:** a registered name that shares no distinctive word with the site is rejected, so a mistyped number cannot attach another company.
- **Storage:** results are observations in the `registry` area that cite the public registry pages.
- **Effects:** they feed people and buyer confidence, the ICP `closed` rule, the brief's company overview, approval contacts (`source = companies_house`) and `account_identifiers`. Duplicate detection matches by identifier, so the same legal entity under another domain joins its existing account.
- **Without a key:** the Companies House step is reported as skipped, and Settings → System shows it as "Needs setup" (`GET /api/v1/system/providers`).

## 6. API

REST under `/api/v1`, OpenAPI generated by FastAPI, typed client generated for the frontend. Cursor pagination for lists. Errors use one problem-details shape. Mutating endpoints write audit entries.

Phase 1 endpoint groups: `auth`, `users`, `team` (active members, for owner pickers), `research-runs`, `prospects`, `accounts` (with timeline and audit), `tasks`, `opportunities`, `config` (ICP and scoring), `catalogue` (services, reference projects; admins complete reference profiles with `PATCH`), `audit`. Errors are `{"error": {"code", "message", "details?"}}`.

## 7. Frontend

Next.js app router, TypeScript, Tailwind. Phase 1 screens: login; Home ("What should I do today?"); New research (URL entry) with live progress; Lead brief review (card with Approve / Reject); Accounts list; Account 360 with Overview, Intelligence, Leads, Tasks, Timeline and Audit tabs; Settings (ICP, scoring weights, service catalogue, reference projects). Fact, Inference and Recommendation are visually distinct everywhere they appear.

**Implemented (slice 1.7):** `frontend/`
- **Rendering:** the signed-in app is client-rendered (`app/(app)/`, one `Suspense` shell). It calls `/api/v1` on the same origin with the session cookie, and sends the CSRF cookie back in `X-CSRF-Token` on every change (`lib/client.ts`). Data comes through SWR (`lib/hooks.ts`), and the research page polls while a run is active.
- **Sign-in redirect:** `proxy.ts` sends visitors without a session cookie to `/login?next=…`. This is only a convenience: the API decides what anyone may see, and a 401 sends the browser to sign in. `next` must be a same-site path.
- **Screens:**
  - **Login.**
  - **Invite acceptance:** the token stays in the URL fragment.
  - **Home:** quick research, the review queue, my open tasks, opportunities requiring attention.
  - **Research:** list and search, including rejected prospects. Each run has its own page with live stage progress and cancel/retry, plus the decision panel with owner, due date, next action, an override reason when the engines disagree, and the duplicate choice. Its tabs are the lead brief (claims with class badges and expandable evidence), opportunities and scores, intelligence, and pages crawled.
  - **Accounts:** list and search, then Account 360 with Overview, Leads, Tasks (complete, reassign, reschedule), Timeline and Audit tabs.
  - **Settings:** profile and password, team invites and roles, services and reference projects (admins complete profiles here), ICP and scoring configuration (versioned JSON editor for admins), system status.
- **Out of scope:** nothing from later phases is shown.
- **Crawled text:** always rendered as text, and links to crawled pages open with `rel="noopener noreferrer nofollow"`.
- **End-to-end test:** `frontend/e2e/phase1.spec.ts` runs in CI (job `e2e`) against Postgres, Redis, the API, a Celery worker, the production build and local fixture websites. The crawler reaches those through `VROS_FETCH_HOST_OVERRIDES`, which is development-only and refused in production.

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
