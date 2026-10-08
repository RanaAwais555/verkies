# VROS Roadmap

Phases follow §20. Phase 1 must work reliably end to end before any later phase starts (§20). Each slice below is demonstrable on its own and ends with passing tests.

## Phase 1: Vertical slice (URL → intelligence → qualification → scoring → CRM)

| Slice | Delivers | Exit criteria |
| --- | --- | --- |
| 1.0 Foundation ✅ | Repo layout, Docker Compose (api, worker, frontend, postgres+pgvector, redis), production overlay (Caddy TLS, single origin, nightly backups), fail-closed production settings, CI (lint, types, tests), health endpoints | `docker compose up` gives a healthy stack; production config refuses insecure settings; CI green |
| 1.1 Schema and auth ✅ | Alembic migrations for DATA_MODEL.md Phase 1 tables, append-only triggers, users/roles/permissions, login, invite-only team onboarding, create-admin CLI, RBAC deps, audit writer | Migration up/down clean; constraint tests pass (unique domain, evidence-required claims, append-only) |
| 1.2 Safe fetch and crawl ✅ | `Fetcher` (httpx, Playwright), SSRF guard, robots, budgets, raw response cache, job runner with stages and progress | SSRF, redirect, rebinding, size and robots tests pass; progress visible via API |
| 1.3 Analysis and evidence ✅ | Website/SEO/conversion/product/technology extractors; observations written as Evidence | Fixture-site tests assert exact observations and evidence fields |
| 1.4 Opportunity, ICP, scoring ✅ | Detectors, ICP and negative-ICP engine, ten dimensions, priority score, gates, bands, config tables and seeds | Unit tests per rule/dimension/gate; golden fixtures pass |
| 1.5 Matching and brief ✅ | Service catalogue and matching, reference projects and similarity (Unknown if no profile), brief assembly, template mode, optional AI mode with grounding validator | Grounding tests: no claim without valid evidence; invented-entity checks pass |
| 1.6 Approval and CRM ✅ | Review queue, approve/reject, Account/Lead/Opportunity/Contact/Task creation in one transaction, dedupe, timeline | Integration test for both paths; rejected prospects off the queue but searchable |
| 1.7 UI ✅ | Login, Home, New research with progress, brief review, Accounts, Account 360, Settings | Playwright e2e of the full DoD checklist (PRODUCT_SPEC.md §4) |

**Phase 1 done** when every box in the §20 checklist passes in the e2e test and the docs match the code.

## Phase 2: Discovery

| Slice | Delivers | Exit criteria |
| --- | --- | --- |
| 2.1 Import and bulk research ✅ | CSV upload with column mapping, validation and a duplicate preview (existing accounts, repeats in the file, similar names, previous research, suppression list), import history, research on chosen rows, account export (CSV/JSON) | Integration tests for every row status and for export safety; browser test of the import flow |
| 2.2 Buying signals ✅ | Job postings from public job-board APIs (Greenhouse, Lever, Ashby, Workable) and news from company blog/press feeds, stored as dated, evidence-backed signals that feed intent and timing | Signals stored with source, date and evidence; scores change only with evidence; fakes in tests |
| 2.3 Company registries ✅ | Companies House (free API key) and Wikidata: identifiers, status, incorporation date, SIC codes, officers as decision makers | Registry facts cited as evidence; dissolved companies rejected as inactive |
| 2.4 Web search discovery ✅ | Self-hosted SearXNG (optional Compose profile) finds candidate company websites; results become a discovery job checked like an import | Provider tests with a fake transport; endpoint tests with a fake provider; browser test against a fake SearXNG |
| 2.5 Search, top leads and duplicates | Plain-English search turned into filters over what VROS knows, "find my next 20 leads" ranking, duplicate review and account merge | Each lead's rank explained; merges audited |

## Later phases

| Phase | Theme | Headline deliverables |
| --- | --- | --- |
| 2 | Discovery | Search providers (CSV, SearXNG, Companies House bulk), deduplication UI, enrichment, job-board and news signals, decision-maker research, natural-language search, top-leads mode |
| 3 | Full CRM and outreach | Contacts, activities, pipelines (New Business, Existing Client Expansion, Partnership), deals, forecasting, unified inbox, mailbox connect with SPF/DKIM/DMARC checks, sequences with approval, LinkedIn assisted queue, suppression and compliance controls |
| 4 | Client lifecycle | Convert Opportunity → Client, projects/milestones, client health, retention engine, expansion engine, referrals, documents |
| 5 | Learning | Feedback capture, win/loss analysis, learned ICP and weight proposals (human-activated), signal effectiveness, similarity learning |
| 6 | Monitoring | Watchlists, website diffs, funding, hiring and leadership changes, alerts and auto-tasks |
| 7 | Hardening | Performance, security review, RBAC refinement, observability (Prometheus/Grafana), backups, DR, scalability |

## Decisions needed (from GAP_ANALYSIS.md §6)

1. Problem signals per confirmed service (`VERKIES_PROFILE.md` §3a), to tune the opportunity detectors.
2. Complete the reference project profiles (`VERKIES_PROFILE.md` §4); until then similarity is Unknown.
3. Production domain and VPS (needed only at go-live; the stack is deployable from slice 1.0).
4. GPU class for Ollama.
5. Initial users and roles.

## Change control

Scope changes update `PRODUCT_SPEC.md` first. Any change to scoring, ICP or AI grounding updates the matching spec in the same pull request.
