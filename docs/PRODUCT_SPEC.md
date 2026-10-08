# VROS Product Specification

The full product definition is `VROS_Master_Context.md`. This document is the working summary for engineers: what Phase 1 delivers, how each requirement is traced, and the rules every feature is checked against. Where this document and the master context disagree, the master context wins and this document gets fixed.

## 1. Purpose

VROS answers, for any company: which companies Verkies should contact, why, who to speak to, what to sell, and what happens next. It is intelligence, qualification, CRM, client lifecycle and learning in one system around a permanent **Account**.

North-Star metric: **Qualified Lead Precision**, the share of recommended prospects a salesperson agrees are worth contacting. Target ≥ 80% initially, ≥ 90% mature. Quality over quantity: 30 right leads beat 1,000 irrelevant ones.

## 2. Rules every feature is checked against

1. Evidence first: no important claim without source URL, collected-at, evidence text, type, confidence (§3).
2. No hallucination: unverified is **Unknown** (§3, AI_SPEC.md).
3. Observation becomes opportunity: never a bare technical fact (§3, §9).
4. Rejection is first-class and auditable (§3).
5. The Account is permanent; no data lost on lifecycle change (§6).
6. No uncontrolled automation; a person approves outreach (§12, §12B).
7. Free and open-source core; paid tools optional behind interfaces (§18, §18A).
8. Everything configurable lives in config tables, not code (§10, §5).
9. No fake or placeholder feature presented as complete (§23).

## 3. Phase 1 scope: the vertical slice

Flow (§20): URL → crawl → extract → opportunities → ICP and negative ICP → scores → evidence → lead brief → approve or reject → Account + Lead + Task → Account 360 with timeline.

### In scope

- Users, roles, login, audit log.
- Research run for a single URL with live stage progress and cancel/retry.
- Safe crawler (robots, limits, SSRF controls) with httpx and Playwright fallback.
- Website, SEO, conversion, product and technology observations stored as Evidence.
- Rule-based opportunity detection across the §9 categories that Phase 1 evidence can support.
- ICP engine, negative-ICP engine, rejection reasons.
- Ten scores, priority score, bands, qualification gate; admin-editable config.
- Service matching (max three) from an admin-editable catalogue.
- Reference-project similarity from admin-supplied profiles; Unknown if none complete.
- Lead brief with Fact / Inference / Recommendation distinction, template mode and optional AI mode.
- Review queue with Approve and Reject (with reason).
- On approve: Account (deduplicated by domain), Lead, Opportunity, Contacts found on public team pages, Task (next action with owner and due date), timeline events.
- Account list and Account 360 (Overview, Intelligence, Leads, Tasks, Timeline, Audit).
- Home page: review queue, due tasks, items requiring attention.

### Out of scope until later phases (do not stub as if present)

Bulk discovery, external company registries, job-board and news signals, monitoring, deals and pipelines, email and LinkedIn outreach, projects and client health, expansion, referrals, learning. UI shows nothing for these in Phase 1 rather than disabled fake screens.

## 4. Acceptance: Definition of Done (§20) mapped to tests

| Requirement | Verified by |
| --- | --- |
| Enter a company URL; start research | API + UI e2e |
| See crawl progress | Stage rows streamed to UI; integration test on stage transitions |
| View company intelligence | Intelligence tab renders observations with evidence links |
| See detected opportunities, ICP score, negative ICP, priority score | Brief renders each; unit tests for engines |
| See evidence and why Verkies should care | Every brief claim links to evidence; grounding validator tests |
| See recommended service and project similarity | Service match + similarity shown, Unknown when no data |
| Approve or reject | e2e both paths; rejected prospects absent from queue, present in search/audit |
| Account created or updated, Lead created, next action created | Integration test in one transaction |
| View account in CRM; complete timeline | Account 360 e2e |

## 5. Lead brief fields (§11)

Company · Priority · ICP Fit · Opportunity · Intent · Buyer Confidence · Data Confidence · Company Overview · Why Verkies · Why Now · Problem Detected · Recommended Service · Best Buyer · Similar Verkies Client/Project · Sales Angle · Risks · Evidence · Recommended Next Action. Any field without evidence shows **Unknown**.

## 6. Phase 1 next-action rule

Approval creates one task: title derived from the recommended next action, owner = approving user unless changed, due date = default SLA from config (2 business days). An opportunity without owner, action or due date is shown as "Opportunity requires attention" (§12).

## 7. Traceability

| Master context | Covered by |
| --- | --- |
| §2–3 principles | This document §2, AI_SPEC.md |
| §5 ICP | ICP_SPEC.md |
| §6 data objects | DATA_MODEL.md |
| §8–9 intelligence, opportunities, signals | ARCHITECTURE.md §5, PROVIDER_SPEC.md |
| §10 scoring | SCORING_SPEC.md |
| §11 brief, similarity, service matching | AI_SPEC.md §4, DATA_MODEL.md |
| §12–15 CRM, outreach, client, learning | ROADMAP.md Phases 3–6 |
| §16 data quality | DATA_MODEL.md §3–4 |
| §17 security | SECURITY.md |
| §18, §18A stack and providers | ARCHITECTURE.md, PROVIDER_SPEC.md |
| §20–21 phases, testing | ROADMAP.md, this document §4 |
