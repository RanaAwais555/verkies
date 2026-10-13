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
| 2.5 Companies House depth and registry discovery ✅ | Filing history (size from the accounts type; dated director appointments, name changes, share allotments, charges as signals), people with significant control, insolvency/dormant review flags; discovery by SIC code, location and age with websites accepted only when they show the same company number | Parser tests, the depth flowing into scores, people, ICP and the brief; discovery end to end against a fake register and local sites |
| 2.6 Search, top leads and duplicates ✅ | Plain-English search turned into filters over what VROS knows, "find my next 20 leads" ranking, duplicate review and account merge | Each lead's rank explained; merges audited |

## Phase 3: Full CRM and outreach

| Slice | Delivers | Exit criteria |
| --- | --- | --- |
| 3.1 Pipelines and deals ✅ | The three default pipelines of §12 (New Business, Existing Client Expansion, Partnership) with ordered stages and default probabilities in config tables; deals opened from an opportunity; a kanban board with the §12 card (company, opportunity, value, owner, priority, next task, last activity, days in stage, probability); stage moves recorded in history, the timeline and the audit log, with a §13 reason required to lose a deal; a forecast (total, weighted, by expected-close month, won, lost) where an unknown value is counted as unknown, never as zero | Integration tests for creating, moving, winning and losing deals, access rules and the forecast arithmetic; browser test of the board |
| 3.2 Activities and contacts ✅ | Log calls, meetings, notes and manual messages against an account, contact, opportunity or deal; edit and add contacts; relationship tracking (first and latest interaction, count, response status); the follow-up engine's flags (overdue follow-up, stale opportunity, no next action, inactive deal) | Activities on the timeline; flags computed from data, tested at their boundaries |
| 3.3 Reporting ✅ | Sales, lead-intelligence and management dashboards from real data; the conversion funnel; saved views | Every figure traceable to its query; empty states, not invented numbers |
| 3.4 Communication ✅ | Mailbox connection behind a provider interface (IMAP/SMTP first), SPF/DKIM/DMARC checks, emails linked to account, contact, opportunity and deal | Provider tests with fakes; nothing sent without explicit configuration |
| 3.5 Outreach ✅ | Templates, sequences with per-step human approval, enrollments, the LinkedIn assisted queue, suppression and compliance controls | Nothing sent automatically; suppression always honoured |

## Phase 4: Client lifecycle

| Slice | Delivers | Exit criteria |
| --- | --- | --- |
| 4.1 Client conversion and projects ✅ | §14 Convert Opportunity → Client from a won deal: the same account becomes a customer with a client-since date and an account manager, and may start a project (owner, service, dates, milestones, kick-off task); lightweight projects with the §6 statuses, milestones, risks, tasks and notes, and the plain facts that need attention (overdue milestones and tasks, high risks, past target, no owner) | Integration tests for conversion (only won deals, never competitors, history kept, first client date kept), project work and access rules; browser test of convert and work a project |
| 4.2 Client health and retention ✅ | Green, Yellow or Red per client from project status, overdue work, communication, open issues and milestones; the retention engine raising "Client Risk Detected" with a follow-up task; former customers; the at-risk clients report | Health computed from data with each colour explained; boundary tests for every rule |
| 4.3 Expansion and referrals ✅ | Evidence-based expansion opportunities on clients (land and expand, §11), referral tracking (source, referred company, status, conversion, revenue), the expansion report | No recommendation without evidence; referral conversion traced to deals |
| 4.4 Documents ✅ | Proposals, contracts, SOWs, briefs and project files stored and linked to their account, deal or project | Upload limits and types enforced; files only visible to people who can see the record |

## Phase 5: Learning

| Slice | Delivers | Exit criteria |
| --- | --- | --- |
| 5.1 Feedback and outcomes ✅ | §15 salesperson feedback (the fifteen kinds) on an account or opportunity; for every deal won or lost, a record of what was true at the close (§13 won-deal data: service, opportunity type, industry, size, geography, source, buyer role, sales cycle, value, dated signals, first and closing scores, most similar reference project), superseded if the deal is reopened; a backfill for deals closed earlier, marked as captured late | Captured in the same transaction as the stage move; Unknown stays Unknown; history never rewritten |
| 5.2 Win/loss analysis ✅ | Win rates and values by industry, size, geography, service, opportunity type, source, buyer role and signal; lost reasons; what feedback said about leads that were won or lost; every figure with its sample size, and small samples marked as too few to learn from | Figures traceable to outcomes; no conclusion drawn from fewer than the minimum sample |
| 5.3 Learned proposals ✅ | Proposed changes to scoring weights and ICP from outcomes, each with the evidence behind it, never active until a person activates it (SCORING_SPEC.md §7) | Proposals reproducible from the same data; activation creates a new versioned config and is audited; human override kept |
| 5.4 Similarity learning ✅ | Won clients become similarity references alongside Verkies' reference projects, so client similarity reflects who actually buys | Similarity still Unknown without complete profiles; tests for the new references |

## Phase 6: Monitoring

| Slice | Delivers | Exit criteria |
| --- | --- | --- |
| 6.1 Watchlists and signal monitoring ✅ | Watch an account; a daily check (and Check now) re-reads the sources its research found (the job boards and news feeds its own site links to, its Companies House record) and stores what it reads as a monitoring check, a run of kind monitor that is never reviewed; a signal not seen before becomes an alert and a timeline line; the Monitoring page lists alerts and watched accounts | Only new signals alert; failing sources reported, never read as no news; monitoring checks never listed or counted as research |
| 6.2 Website changes ✅ | The monitoring check re-reads the pages research read and compares each with the last copy kept: pages newly linked from or dropped from the homepage, pages now 404 or 410, changed text, and services, pricing, technology and contact routes added or removed; each is a website alert with the text before and now | A change only when the content differs, with before and after evidence; an unreachable page is an error, never a removal; reported once |
| 6.3 Alert rules and auto-tasks ✅ | Rules from §15 (five seeded, admin-editable) match new alerts by kind, signal and website topic, and raise Opportunity Detected or Account Requires Review (until the alerts are reviewed) or create one follow-up task for the account's manager or owner; in-app notifications with a bell, per-person kinds | Each rule tested; nothing contacts anyone |

## Phase 7: Hardening

| Slice | Delivers | Exit criteria |
| --- | --- | --- |
| 7.1 Observability ✅ | Prometheus metrics on the API's internal port (requests and latency by route template, work in hand, worker task outcomes and last success), an `observability` Compose profile with Prometheus, alert rules and a provisioned Grafana dashboard | /metrics never answered on the public hostname and carries no personal data; rules load; dashboard shows live data |
| 7.2 Backups and disaster recovery ✅ | Daily dump and documents archive encrypted with age to an offline key and copied off-site with rclone (never unencrypted), a weekly restore drill, every step recorded and shown in Settings and metrics with alerts, a fetch-and-decrypt script and a written rebuild procedure (RPO one day, RTO about an hour) | A restore from the off-site copy is tested end to end |
| 7.3 Security review ✅ | SECURITY.md compared with the code: rate limits (sign-in and invites per address, password changes, research and the API per person), real client addresses behind Caddy, a CSP and cross-origin headers, dependency audits in CI, a k-anonymity breached-password check; sessions, CSRF, SSRF and uploads re-checked | Each finding fixed or recorded with its reason (SECURITY.md §9) |
| 7.4 Access control refinement ✅ | Permission matrix reviewed; Viewer made truly read-only (`records.write`, required centrally for changes allowed only by read access; personal actions marked); a test that reads every route from the schema and checks strangers, no-role users, Viewers and other people's accounts; "View only" label | Every endpoint covered by an access test |
| 7.5 Performance and scale ✅ | Load-tested at 20,000 accounts (docs/PERFORMANCE.md): the follow-up engine moved into SQL with capped lists and exact counts (52 s to 0.6 s), an index on `tasks.opportunity_id`, several API processes with combined metrics, configurable worker concurrency, and a test that every list endpoint is bounded; what is still slow is recorded | Baseline recorded; no list endpoint unbounded |

## Phase 8: Prospect finder

Discovery starts from complete, official lists of real organisations (regulators' registers and open datasets) instead of web pages, so a search returns firms and not articles; each prospect then carries fit, need, timing and reach with evidence.

| Slice | Delivers | Exit criteria |
| --- | --- | --- |
| 8.1 Registers kept in VROS ✅ | A register source framework (adapter per register: download, cadence, parse, attribution), `register_sources` and `register_records` with first seen, last seen and removed; the worker checks hourly and refreshes each source on its own cadence, applying only a changed download and refusing a short one; Settings, System shows each register's last refresh with Refresh now (admins); the SRA register through its Data Share API; Discover searches it by area of work, office location (London or postcode areas), offices, specialisms and authorisation date into a checked discovery job with the register's website and company number | A failing or short download leaves the copy untouched and says why; an identical download is not applied; removed firms are marked, never deleted; every route covered by the access test |
| 8.2 Website compliance and health ✅ | A compliance extractor over every crawled page (observation area `compliance`): for a site that names the SRA, its digital badge, SRA number, complaints procedure naming the Legal Ombudsman and published prices for immigration work; for a site that names a limited company or LLP, its registered number; trackers loaded with no cookie consent tool. In the enrich stage, the Wayback Machine (how long the homepage has gone unchanged) and Google Safe Browsing (optional key). A "Website compliance fixes" opportunity when a regulator's rule is missed, the site is listed as unsafe, or two other gaps are found; an archive unchanged three years or more counts towards "Website rebuild" | Every finding names the page it came from, and every absence how many pages were checked; a rule applies only when the site says what makes it apply; outside checks that are off or failing are reported, never read as all clear |
| 8.3 More registers ✅ | The IAA's regulated organisations (GOV.UK spreadsheet, found through the publication page so a new release is picked up), every school in England (DfE's GIAS daily CSV, with the head teacher), and the Charity Commission's register (daily extract with each charity's latest income and what it does), as register sources beside the SRA. Refresh rewritten for size: plain SQL in batches with a content hash per record, so the 172,000-charity register loads without an object per row and a later refresh rewrites only what changed. Discover searches any register with the filters it supports (location, offices, income, specialists); job titles read "Charities: …" | Each source tested in the publisher's format and against the real download (IAA 2,274, schools 52,589 of which 27,158 open, charities 171,891); a short, failed or unchanged download handled as for the SRA; licence attribution shown with the data |
| 8.4 Triggers | Companies House streaming (name changes, new directors, office moves, share allotments), accounts data (employee growth), new authorisations and registrations, tenders | Each trigger dated with its source; fades after its window |
| 8.5 Four-axis prospect score | Fit, need, timing and reach as separate scores, a High-fit default view with the reason each result was hidden | Every score traceable to evidence; precision of the top 20 measured |
| 8.6 Website matching and more datasets | Find the website of register entries that lack one (Legal Aid providers, visa sponsors, ICO register) by Companies House number and Overture places; then CQC, the visa sponsor register, the ICO register (size tiers) and Overture as sources | A website is accepted only with evidence it is the same organisation |

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
