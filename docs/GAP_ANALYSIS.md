# VROS Gap Analysis

Date: 2026-10-08 · Compared against: `docs/VROS_Master_Context.md` v1.1

## 1. What exists

The repository is greenfield. It holds one commit (`Initial commit`) containing a one-line `README.md`. There is no code, schema, configuration, CI, container setup or documentation to preserve or restructure.

## 2. Build environment

| Tool | Present | Notes |
| --- | --- | --- |
| Python 3.13 | yes | Backend runtime |
| Node 22 | yes | Frontend runtime |
| Docker 29 | yes | Compose target for deployment |
| PostgreSQL 16 client | yes | pgvector and pg_trgm availability to be confirmed in the Compose image |
| Redis 7 | yes | Queue and cache |
| Ollama | **no** | Local AI is unavailable in this session. AI features must degrade gracefully (AI_SPEC.md §6) and be tested against a fake provider. |

## 3. Gap by area

Every requirement in the master context is currently a gap. The table orders them by the build order in Section 23 and marks what the first vertical slice (Phase 1) must close.

| Area | Master context | Status | Phase |
| --- | --- | --- | --- |
| Engineering documents | §21 | Closed by this change | pre-code |
| Data model (Account-centric) | §6, §16 | Missing | 1 (core tables), later phases extend |
| Auth, RBAC, audit log | §17 | Missing | 1 (users, roles, audit); 7 (hardening) |
| Provider abstraction | §18 | Missing | 1 (fetch, AI, storage, search stub); later per module |
| Crawler (robots, rate limits, SSRF) | §17, §18A | Missing | 1 |
| Website, SEO, conversion, product, technology analysis | §8 | Missing | 1 |
| Evidence store and Fact/Inference/Recommendation tagging | §3, §18 | Missing | 1 |
| Opportunity detection | §9 | Missing | 1 |
| ICP and negative-ICP engine | §5 | Missing | 1 |
| Scoring (10 dimensions, priority score, bands) | §10 | Missing | 1 |
| Lead brief and lead card | §11 | Missing | 1 |
| Service matching | §11 | Missing, **blocked on service catalogue** (§6 below) | 1 |
| Similar client engine | §11 | Missing, **blocked on reference-project data** (§6 below) | 1 (structure + simple similarity), 5 (learned) |
| Approve / reject, Account + Lead + Task creation | §20 | Missing | 1 |
| Account 360 and timeline | §12 | Missing | 1 (Overview, Intelligence, Leads, Tasks, Timeline, Audit tabs); rest later |
| Job runner with progress | §18 | Missing | 1 |
| Discovery, dedup, enrichment, decision makers, buying-signal feeds | §9, §15, §18A | Missing | 2 |
| Full CRM (contacts, pipelines, deals, forecasting) | §12, §13 | Missing | 3 |
| Email and LinkedIn outreach | §12A, §12B | Missing | 3 |
| Client lifecycle (projects, health, retention, expansion, referrals) | §14 | Missing | 4 |
| Feedback, win/loss, learning engine | §15 | Missing | 5 |
| Monitoring | §15 | Missing | 6 |
| Observability, backups, DR, security review | §17, §18 | Missing | 7 |

## 4. Risks and constraints

1. **No hallucination rule vs. AI-written briefs.** The brief's prose is AI-generated, so every sentence must be traceable. Mitigation: AI input is restricted to stored evidence items with IDs, output is schema-validated, and any claim that cites no real evidence ID is dropped or shown as Unknown (AI_SPEC.md).
2. **Ollama not available here.** Opportunity detection, ICP evaluation and scoring are deterministic rules, so the slice works end to end without a model. AI adds the prose layer and is optional.
3. **Reference clients are only partly known.** The six archetypes (Wesbridge Associates, Oerno, ShiftRow, THEOO, LumiNexis TBG, Ask iDeer) are described on the public site, but only at marketing level (`VERKIES_PROFILE.md`). The system must not invent the missing fields.
4. **JS-heavy sites.** The static fetch will under-read some sites. Playwright fallback is in Phase 1 but kept behind the same fetch interface.
5. **Crawler is an SSRF surface** because users submit URLs. SSRF controls are Phase 1 scope, not Phase 7 (SECURITY.md §3).
6. **Scope size.** The master context describes 38 modules. Only the Phase 1 vertical slice is committed to here.

## 5. Target architecture

See `ARCHITECTURE.md`. In one line: a modular FastAPI monolith with a Celery worker, PostgreSQL (pgvector, pg_trgm) as the only datastore of record, Redis for queue and cache, a Next.js frontend, and every external dependency behind a provider interface.

## 6. Decisions needed from Verkies

These do not block the documents. Items 1 and 2 block the *content* of two Phase 1 features.

1. **Verkies service catalogue: resolved.** Verkies confirmed fifteen services on 2026-10-08 (`VERKIES_PROFILE.md` §3a). Still useful: the problem signals each service answers, to tune the opportunity detectors.
2. **Reference project profiles: partly resolved.** Names, industry, service delivered and status for all six archetypes are in `VERKIES_PROFILE.md` §4. Technologies, company size, growth stage, buyer role and value are **Unknown** and stay so until Verkies fills them in; similarity returns Unknown until a profile is complete.
3. **ICP priority between two buyer types** (founder MVP vs. service-firm CRM/website), see `VERKIES_PROFILE.md` §5.
4. **Production domain and VPS.** VROS is built for team use on a live domain (single origin behind Caddy, `ARCHITECTURE.md` §9). The domain and server are only needed at go-live.
5. **GPU class** of the machine that will run Ollama (8, 16 or 24 GB). Picks the default models in `AI_SPEC.md` §5.
6. **Initial users and roles** to seed.

## 7. Proposed next step

Implement the Phase 1 vertical slice per `ROADMAP.md`. Slices are ordered so each is demonstrable on its own: schema and auth, then crawler and evidence, then analysis and scoring, then brief and approval, then the UI.
