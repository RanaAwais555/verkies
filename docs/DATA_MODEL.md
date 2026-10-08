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
**account_identifiers**: `account_id`, `scheme` (companies_house, sec_cik, wikidata, …), `value`; unique `(scheme, value)`.

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
**activities**: `account_id`, optional links as for tasks, `channel`, `activity_type`, `occurred_at`, `actor_id`, `summary`, `payload jsonb`.
**timeline_events**: append-only read model: `account_id`, `occurred_at`, `event_type`, `ref_table`, `ref_id`, `summary`. Written by services at the moment of the event (company discovered, website analysed, lead qualified, task created, …).

Constraint: every open opportunity must have a next-action task with owner and due date, or it is returned by the "requires attention" query (§12).

### Audit

**audit_log** (append-only): `occurred_at`, `user_id` null (system), `object_table`, `object_id`, `action`, `old_value jsonb`, `new_value jsonb`, `source` (ui, api, worker, import), `reason`.

### Suppression

**suppressions**: `kind` (email, domain, account), `value`, `reason`, `added_by`, `added_at`. Checked before any research approval creates an owner-assigned lead (§5 "suppressed account").

## 3. Duplicate handling (§16)

On research start and on approval, candidates are looked up by normalised domain (exact via `account_domains`), name similarity (`pg_trgm` ≥ 0.6), and identifiers. A hit is never merged silently: the run is flagged `possible_duplicate_of` with the matching accounts and the reviewer decides.

## 4. Search

`pg_trgm` indexes on account names and domains exist from Phase 1 (duplicate detection). `tsvector` generated columns and the single `search` service fanning out over accounts, contacts, leads, opportunities, tasks and evidence (§16) are added in the slice that builds global search.

## 5. Tables added in later phases (names reserved)

| Phase | Tables |
| --- | --- |
| 2 | `discovery_jobs`, `discovered_companies`, `buying_signals`, `signal_sources`, `job_postings` |
| 3 | `pipelines`, `pipeline_stages`, `deals`, `communications`, `meetings`, `proposals`, `documents`, `mailboxes`, `templates`, `sequences`, `sequence_steps`, `enrollments`, `messages`, `linkedin_imports` |
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
