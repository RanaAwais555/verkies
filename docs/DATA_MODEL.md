# VROS Data Model

Relational PostgreSQL 16 with pgvector and pg_trgm. Account-centric (§6). This document defines the Phase 1 schema in full and names the tables later phases add, so Phase 1 never needs a destructive rewrite.

## 1. Conventions

- Primary key `id uuid` (UUIDv7).
- `created_at`, `updated_at` as `timestamptz not null`, set by the database or ORM.
- `deleted_at timestamptz null` on user-facing entities. Evidence, audit and timeline rows are append-only and never soft-deleted.
- Enumerations are Postgres enums or `text` with a `CHECK`; never free text.
- Foreign keys are always declared. `ON DELETE RESTRICT` unless stated.
- Scores are `numeric(5,2)` in `[0, 100]`, nullable. **Null means Unknown**, never zero.
- Indexes: every foreign key, plus those listed below.

## 2. Phase 1 tables

### Identity and access

**users**: `email` (citext, unique), `name`, `password_hash`, `is_active`, `last_login_at`, `failed_login_count`, `locked_until`.
**user_sessions**: `user_id`, `token_hash` (HMAC of the cookie token, unique), `last_seen_at`, `expires_at`, `revoked_at`, `ip`, `user_agent`.
**invites**: `email` (citext), `token_hash` (unique), `invited_by_id`, `expires_at`, `accepted_at`, `accepted_user_id`, `revoked_at`; **invite_roles** links the roles granted on acceptance.
**roles**: `key` (unique): admin, founder, sales_manager, salesperson, researcher, project_manager, viewer. **user_roles**: `user_id`, `role_id`, unique pair.
**permissions** and **role_permissions** hold configurable RBAC (§17).

### Account (central entity)

**accounts**
- `name`, `legal_name`, `primary_domain` (normalised, unique where `deleted_at is null`), `website_url`
- `industry`, `sub_industry`, `business_model`, `description`
- `hq_city`, `hq_country` (ISO-3166 alpha-2), `company_size_band`, `estimated_revenue` (only when verified)
- `account_type` enum: prospect, qualified_prospect, opportunity, customer, former_customer, partner, competitor, suppressed. This is the lifecycle state (§6).
- `agency_class` enum null: competitor, potential_partner, referral_partner, white_label_partner, subcontracting
- `owner_id` → users, `source`
- Cached latest scores: `icp_score`, `opportunity_score`, `intent_score`, `buyer_confidence`, `data_confidence`, `service_fit`, `timing_score`, `commercial_potential`, `client_similarity`, `evidence_strength`, `priority_score`, `priority_band`
- `last_activity_at`, `next_activity_at`
- `linkedin_company_url`, `linkedin_employee_range`, `linkedin_employee_range_at` (nullable; used from Phase 3)

Cached scores are denormalised copies of the latest `score_snapshots`; the snapshot is the source of truth.

**account_domains**: `account_id`, `domain` (unique, normalised), `is_primary`. Supports duplicate detection (§16).
**account_identifiers**: `account_id`, `scheme` (companies_house, sec_cik, wikidata, …), `value`; unique `(scheme, value)`. Written on approval from registry facts (slice 2.3); duplicate detection treats a shared identifier as the same legal entity.

Indexes: trigram on `accounts.name`, `account_domains.domain`; btree on `account_type`, `owner_id`, `priority_score desc`.

### Evidence (the source behind every claim)

**evidence** (append-only)
- `account_id` (nullable until the prospect is approved), `research_run_id`
- `source_url`, `source_domain`, `collected_at`, `published_at` null
- `evidence_type` enum: page_content, http_header, dns_record, structured_data, technology_fingerprint, job_posting, company_registry, news_item, user_note, other
- `evidence_text` (the supporting excerpt), `content_hash`
- `confidence numeric(3,2)` in `[0,1]`
- `raw_response_id` → `raw_responses` (cached fetch)

**raw_responses**: `url`, `final_url`, `rendered`, `fetched_at`, `status_code`, `headers jsonb` (never `Set-Cookie`), `body_ref` (content-addressed storage key), `content_type`, `bytes`, `content_hash`. Unique on `(url, rendered, content_hash)`; refetching identical content refreshes `fetched_at`.

**observations**: a structured fact from a crawled site (catalogue: `OBSERVATIONS.md`). `research_run_id`, `attempt` (the run's retry count when produced; the API shows the latest), `account_id` (attached on approval), `area` (website, seo, conversion, product, technology, company, hiring), `key`, `value jsonb`, `evidence_id` (exactly one evidence row), `seen_on jsonb`, `confidence`. Append-only.

**claims**: a stated finding in the system. `account_id`, `research_run_id`, `claim_class` enum (fact, inference, recommendation), `subject` (e.g. `conversion.primary_cta`), `statement`, `confidence`.
**claim_evidence**: `claim_id`, `evidence_id`. A `fact` claim must have at least one row, enforced by a deferred constraint trigger. An `inference` must too. A `recommendation` links to the claims it rests on via `claim_support`.

### Research runs and jobs

**research_runs**: `input_url`, `normalised_domain`, `account_id` null (set on approval or when matched to an existing account), `requested_by`, `status` (queued, running, completed, failed, cancelled, retrying), `review_status` (pending, approved, rejected), `started_at`, `finished_at`, `error`, `retry_count`, `crawl_budget jsonb`.
**research_stages**: `research_run_id`, `stage` (validate, crawl, extract, detect, qualify, score, match, brief), `status`, `progress_pct`, `started_at`, `finished_at`, `detail jsonb`, `error`. Drives the progress UI. A run only gets rows for the stages that exist in the pipeline today (validate and crawl as of slice 1.2); later slices add theirs.
**research_pages**: what a run fetched, reused, skipped or was refused: `kind` (page, robots, sitemap), `url`, `final_url`, `discovered_via` (start, link, sitemap, robots), `category`, `status_code`, `content_type`, `bytes`, `raw_response_id`, `from_cache`, `rendered`, `title`, `canonical_url`, `duplicate_of_url`, `fetched_at`, `skip_reason`, `error`. Analysis (slice 1.3) reads pages from here.

### Opportunity detection

**opportunity_categories**: configurable catalogue seeded from §9 (MVP development, SaaS development, … ongoing product support). `key`, `name`, `service_id` null.
**opportunity_candidates**: output of detectors in a run. `research_run_id`, `category_id`, `title`, `problem_statement`, `confidence`, `rule_key`. **opportunity_candidate_evidence** links to `evidence`.

### Qualification and scoring

**icp_configs**: versioned, `is_active`. `config jsonb` holds industry tiers, geography, negative ICP rules (ICP_SPEC.md). One active row.
**scoring_configs**: versioned, `is_active`. `config jsonb` holds dimension weights, band thresholds, gates (SCORING_SPEC.md).
**qualification_results**: `research_run_id`, `icp_config_id`, `icp_fit`, `negative_icp_hits jsonb`, `hard_reject bool`, `rejection_reason` enum null, `explanation`.
**score_snapshots**: `research_run_id` or `account_id`, `scoring_config_id`, ten dimension columns, `priority_score`, `priority_band`, `breakdown jsonb` (per-dimension inputs, weights, contributions, and which inputs were Unknown), `created_at`. Append-only.

Rejection reason enum (§3): no_commercial_opportunity, wrong_icp, inactive_company, duplicate, competitor, insufficient_evidence, no_relevant_service, no_reachable_buyer, hobby_or_personal, student_or_freelancer, unsuitable_company_size, irrelevant_industry, existing_solution_sufficient, suppressed_account.

### Services and similarity

**services**: Verkies service catalogue. `key`, `name`, `description`, `solves jsonb` (opportunity category keys), `source_url`, `confirmed bool`, `parent_service_id` null (for unconfirmed capabilities), `is_active`. Seeded from `VERKIES_PROFILE.md` §3a: fifteen services, all `confirmed=true`. A service added later starts unconfirmed; service matching only recommends confirmed services.
**reference_projects**: `name` (unique), `industry`, `business_model`, `problem`, `technologies text[]`, `status`, `website_url`, `growth_stage`, `buyer_type`, `workflow_notes`, `source_url`, `profile_complete bool`, `embedding vector(768)` null. Seeded from `VERKIES_PROFILE.md` §4 with only the fields the public site states; the rest are null (Unknown) and `profile_complete=false` until an admin fills them in. **reference_project_services** links each project to the services delivered.
**service_matches**: `research_run_id`, `slot` (primary, secondary, expansion), `service_id`, `rationale`, `confidence`. At most three per run (`unique(research_run_id, slot)`).
**similarity_results**: `research_run_id`, `reference_project_id`, `similarity_score`, `similar_because`.

### Lead brief

**lead_briefs**: `research_run_id` (unique), `account_id` null, all fields from §11 as columns or `jsonb` sections, each section holding claim IDs. `generated_by` (`template` or provider+model), `generated_at`.

### CRM core (Phase 1 subset)

**leads**: `account_id`, `research_run_id`, `source`, `owner_id`, `status` (new, qualified, researching, contacted, engaged, rejected, nurture, converted), `score_snapshot_id` (all ten scores), `priority_score` and `priority_band` (copied for sorting the queue), `qualified_at`, `rejection_reason`, `rejection_note`. `campaign_id` arrives with campaigns.
**opportunities**: `account_id`, `lead_id`, `name`, `problem`, `category_id`, `service_id`, `estimated_value` null, `currency`, `probability` null, `expected_close` null, `stage`, `owner_id`, `next_action_task_id`.
**contacts**: `account_id`, `name`, `title`, `department`, `email` null, `phone` null, `profile_url` null, `source`, `source_url`, `collected_at`, `confidence`, `decision_maker_role` enum (§6), `verification_status` (unverified, verified), `linkedin_url`, `linkedin_connection_status`. Phase 1 stores contacts found on team pages; email is stored only if published on the page.
**tasks**: `account_id` (required), optional `contact_id`, `lead_id`, `opportunity_id`; `title`, `description`, `owner_id`, `due_at`, `priority`, `status`, `recurrence`, `completed_at`. `deal_id` and `project_id` are added with deals (Phase 3) and projects (Phase 4).
**activities**: `account_id`, optional links as for tasks plus `deal_id` (slice 3.2), `channel`, `direction` (outbound, inbound, conversation, internal; slice 3.2), `activity_type` (call, meeting, note, message), `occurred_at`, `actor_id`, `summary`, `payload jsonb` (a call's `call_outcome`). See §4b.
**timeline_events**: append-only read model: `account_id`, `occurred_at`, `event_type`, `ref_table`, `ref_id`, `summary`. Written by services at the moment of the event (company discovered, website analysed, lead qualified, task created, …).

Constraint: every open opportunity must have a next-action task with owner and due date, or it is returned by the "requires attention" query (§12).

### Audit

**audit_log** (append-only): `occurred_at`, `user_id` null (system), `object_table`, `object_id`, `action`, `old_value jsonb`, `new_value jsonb`, `source` (ui, api, worker, import), `reason`.

### Suppression

**suppressions**: `kind` (email, domain, account), `value`, `reason`, `added_by`, `added_at`. Checked before any research approval creates an owner-assigned lead (§5 "suppressed account").

### Discovery (Phase 2, migration `0008`)

**discovery_jobs**: `kind` (csv_import), `name` (file name), `created_by_id`, `status` (uploaded, checked), `columns jsonb` (header row), `mapping jsonb` (field → column), `row_count`, `stats jsonb` (rows per status).
**discovered_companies**: one row of an import. `discovery_job_id` (cascade), `row_number` (unique per job), `raw jsonb` (the row as uploaded), mapped `name`, `website_url`, `normalised_domain`, `country`, `industry`, `notes`, `status` (pending, new, invalid, duplicate_in_file, existing_account, possible_duplicate, already_researched, suppressed, queued), `status_detail`, `matched_account_id`, `research_run_id`. A discovered company is never an Account; it can only become one through research and approval.

## 3. Duplicate handling (§16)

On research start and on approval, candidates are looked up by normalised domain (exact via `account_domains`), name similarity (`pg_trgm` ≥ 0.6), and identifiers. A hit is never merged silently: the run is flagged `possible_duplicate_of` with the matching accounts and the reviewer decides.

As implemented (slice 1.6):
- An exact domain match means the same company: approval attaches to that account. Its name, owner and description are kept, its cached scores are refreshed, and a `prospect` becomes a `qualified_prospect`.
- A name match blocks approval until the reviewer either chooses the account (the new domain is added to it) or confirms a new company.
- Contacts are de-duplicated by name within the account.
- Identifier matching arrives with the registries in Phase 2.

Duplicate review and merge (slice 2.6, migration `0013`):
- `GET /account-duplicates` suggests live account pairs with similar names (`pg_trgm` ≥ 0.6), the same legal name, or the same website name under a different ending (`harbour.test` / `harbour.co.uk`). Pairs a reviewer marked as different companies (`account_duplicate_dismissals`, one row per pair, smaller id first) are not suggested again.
- `POST /accounts/{keep}/merge` (permission `accounts.merge`: Admin, Founder, Sales Manager; a reason is required) moves the mutable rows to the kept account: domains (as extra domains), identifiers, contacts, leads, opportunities, tasks, activities, research runs, lead briefs and discovery matches. The kept account takes any field it has no value for, the earlier next activity and the later last activity. Everything happens in one transaction with an `account.merged` audit entry and a timeline event.
- Evidence, claims, observations, score snapshots and timeline events are append-only (§6), so they stay on the retired account. It is soft-deleted with `merged_into_id` pointing at the survivor (chains are re-pointed, so one level), and the survivor's timeline and audit read include it. Opening a retired account returns `404` with code `merged` and `details.merged_into`, which the app follows.

## 4. Search

`pg_trgm` indexes on account names and domains exist from Phase 1 (duplicate detection). `tsvector` generated columns and the single `search` service fanning out over accounts, contacts, leads, opportunities, tasks and evidence (§16) are added in the slice that builds global search.

Lead search (slice 2.6, `backend/app/leads`): `GET /leads/search?q=` reads a plain-English request with deterministic rules (`interpret.py`, no AI) into filters over accounts: industry, city, country, opportunity categories (any of), dated buying signals (each one required, within a window), priority band, account type and owner. Words that match no rule become a visible "name, industry or description mentions" filter; requests that cannot be answered yet (similarity to a client) are reported as unsupported, never guessed. `GET /leads/top` is the same ranking restricted to open, scored prospects outside the Reject band and the suppression list. Results are ordered by the stored priority score (then timing, data confidence, least recently touched), and each one is explained from its latest score snapshot's breakdown, dated signals with their source, and open opportunities.

## 4a. Pipelines and deals (slice 3.1, migration `0014`)

**pipelines**: `key` (unique), `name`, `kind` (new_business, expansion, partnership), `position`, `is_active`. Seeded with the three §12 defaults.

**pipeline_stages**: `pipeline_id`, `key` (unique per pipeline), `name`, `position`, `probability` (0-100, NULL for partnership stages: nothing to weight), `outcome` (open, won, lost, nurture, inactive). Editable by `config.manage` (`PATCH /pipeline-stages/{id}`, audited).

**deals**: `account_id`, `opportunity_id` (at most one live deal per opportunity), `pipeline_id`, `stage_id`, `name`, `value` (entered by a person; NULL is Unknown, never estimated), `currency`, `probability` (overrides the stage default when set), `expected_close`, `owner_id`, `outcome` (copied from the stage on every move), `stage_entered_at` (days in stage), `closed_at` (won, lost or inactive), `lost_reason` (required when lost; the §13 list), `lost_note`, soft delete.

**deal_stage_changes**: `deal_id`, `from_stage_id`, `to_stage_id`, `changed_by_id`, `changed_at`: every stage a deal passed through, for the conversion funnel (slice 3.3).

`tasks.deal_id` links a task to a deal; a deal's task is also its opportunity's next action. A move also sets the opportunity's `stage` to the stage key, writes the timeline and the audit log, and an account merge carries its deals with it. The forecast (`GET /deals/forecast`) groups by currency and counts deals without a value, without a probability or without a close date instead of treating them as zero.

## 4b. Activities, relationships and follow-ups (slice 3.2, migration `0015`)

`activities` gains `deal_id` and `direction`, with indexes on (account, time), (contact, time), opportunity and deal. `POST /activities` logs one (the kind sets the channel and direction: a connected call or a meeting is a conversation, an unanswered call or a sent message is outbound, a received message inbound, a note internal), writes a timeline event dated `occurred_at` and an `activity.logged` audit entry, and can create the follow-up task in the same transaction. Activities are not edited through the API. They move with an account merge and are part of the account's audit view.

Relationship tracking has no table: it is folded from a contact's (or an account's) activities on read (`app/crm/activities.py`), so it always agrees with them.

Contacts: `POST /accounts/{id}/contacts` and `PATCH /contacts/{id}` (`source` "manual", confidence 1.00, unverified until marked). Suppressed emails and domains are refused; an email already on the account is a 409. Creation writes the timeline; both write the audit log.

`GET /follow-ups[?mine=true]` returns the follow-up engine's flags (overdue follow-up, no next action, stale opportunity, inactive deal) with the thresholds used. "Something happened" means a logged activity or a completed task on the opportunity or deal, or a deal's stage move; a record's creation starts the clock. Deals also show "inactive for N days" among their attention reasons on the board.

## 4c. Reports and saved views (slice 3.3, migration `0016`)

Reports have no tables: every dashboard figure is a query over the records above, run on request and limited to the accounts the user may see (`app/reports/service.py`). Each figure and breakdown carries its rule in words (`definition`) and, where a page lists the records, a link (`href`). Endpoints: `GET /reports/sales` (accounts.read or accounts.read_own; `?mine=true` for the user's own work), `GET /reports/lead-intelligence` (accounts.read or prospects.review) and `GET /reports/management` (new permission `reports.team`: Admin, Founder, Sales Manager), each with `period` = 7d, 30d, 90d, 365d or ytd. The conversion funnel follows the websites first researched in the period and counts each company at the furthest step it reached.

**saved_views**: `user_id` (NULL is a team view), `name`, `path` (a VROS page that keeps its filters in the address), `query` (its query string), `position`, `created_by_id`. Only the link is stored, so a view always shows current data through the page's own permissions. `GET/POST /saved-views`, `DELETE /saved-views/{id}`; sharing or removing a team view needs `config.manage` and is audited. Migration 0016 seeds the team's eight starting views.

## 4d. Mailboxes and email (slice 3.4, migration `0017`)

**mailboxes**: one per user (`user_id` unique): `address`, `display_name`, `provider` (imap_smtp), SMTP and IMAP host and port, `smtp_security` (ssl, starttls), `username`, `secret_encrypted` (Fernet, key from `VROS_SECRET_KEY` via HKDF; NULL once disconnected), `status` (unverified, connected, failing, disconnected), `last_error`, `verified_at`, `dkim_selector`, `dns_checks` (mx, spf, dkim, dmarc: status, record, advice), `dns_checked_at`, `sending_enabled`, `daily_cap`, `imap_uidvalidity` and `imap_last_uid` (where reading resumes), `last_synced_at`.

**email_messages**: `mailbox_id`, `account_id`, `contact_id`, `opportunity_id`, `deal_id`, `direction` (outbound, inbound), `status` (sent, failed, received, bounced), `message_id_header` (unique per mailbox), `in_reply_to`, `thread_key` (the first message's Message-ID), addresses, `subject`, `body_text`, `occurred_at`, `sent_by_id`, `activity_id` (the timeline activity), `error`, `classification` (opt_out). Endpoints: `GET/PUT/DELETE /mailbox`, `POST /mailbox/check`, `POST /mailbox/sync`, `GET /email/preflight?contact_id=`, `POST /email/send`, `GET /email/messages`.

## 5. Tables added in later phases (names reserved)

| Phase | Tables |
| --- | --- |
| 2 | `discovery_jobs` and `discovered_companies` exist since slice 2.1. Buying signals (slice 2.2) are observations in the `signals` area with dated evidence (migration `0009`), so they share evidence, attempts and append-only history with all other findings; no separate signal tables were needed |
| 3 | `pipelines`, `pipeline_stages`, `deals` and `deal_stage_changes` exist since slice 3.1; logged meetings, calls and messages are `activities` (slice 3.2), and `meetings` stays reserved for scheduled meetings with calendar sync; `mailboxes` and `email_messages` (the §12B Message object for email) exist since slice 3.4; `proposals`, `documents`, `templates`, `sequences`, `sequence_steps`, `enrollments`, `messages`, `linkedin_imports` |
| 4 | `projects`, `milestones`, `project_risks`, `client_health_snapshots`, `expansion_opportunities`, `referrals` |
| 5 | `feedback`, `deal_outcomes`, `learned_weights` |
| 6 | `monitors`, `monitor_snapshots`, `monitor_events` |

## 6. Integrity rules enforced in the database

Implemented in migration `0002_integrity_rules` and covered by `tests/integration/test_integrity.py`.

- A `fact` or `inference` claim must cite at least one evidence row, and a `recommendation` must rest on at least one other claim. Checked at commit (deferred constraint trigger), so rows can be inserted in any order.
- `evidence`, `observations`, `claims`, `claim_evidence`, `claim_support`, `score_snapshots`, `audit_log` and `timeline_events` reject `UPDATE` and `DELETE`. The single exception: `account_id` on evidence, observations, claims and score snapshots may be set once from NULL (attaching research to the Account on approval); any other change in the same statement is refused.
- `accounts.primary_domain` is unique among non-deleted accounts.
- Scores are within `[0, 100]` (NULL means Unknown); confidence within `[0, 1]`.
- Enumerations are text columns with CHECK constraints.
- At most one active `icp_configs` and one active `scoring_configs` row.
- `service_matches` has at most one row per slot (primary, secondary, expansion), so at most three per run.
- `leads.research_run_id` is unique (migration `0007`): a research run becomes at most one lead, so a prospect cannot be approved twice.
