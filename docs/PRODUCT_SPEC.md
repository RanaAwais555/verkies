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

### Phase 3, slice 3.1: pipelines and deals (§12, §13)

- Pipelines and their stages are config (`pipelines`, `pipeline_stages`), seeded with the three §12 defaults. Each stage has an order, a default probability and an outcome: open, won, lost, nurture or inactive. Partnership stages carry no probability: a partnership has no revenue to weight, so it is left out of the weighted forecast rather than counted as zero.
- A deal belongs to an account and usually to the opportunity it was opened from. Its value, currency and expected close date are entered by a person; VROS never estimates a deal value. A deal without a value shows **Unknown** and is counted separately in the forecast.
- Moving a deal records the change (stage history, timeline, audit). Losing one requires a §13 lost reason. Winning one closes it. It does not yet convert the account to a client; that is Phase 4's client conversion.
- An open deal without an open next task, an owner or an expected close date is flagged on its card, in the spirit of §12's next-action engine.
- The forecast shows total pipeline, weighted pipeline, expected value by close month, and won and lost value, each from the deals themselves.

### Phase 3, slice 3.2: activities and contacts (§12)

- A person logs a call, meeting, note or manual message after it happened, against an account and optionally a contact, an opportunity and a deal. A call records how it went (connected, no answer, voicemail); a message records its channel (email, LinkedIn, WhatsApp, other) and who sent it. Activities cannot be in the future and are never edited; a correction is a new note. VROS records; it never contacts anyone itself.
- Each activity appears on the account timeline at the moment it happened, is audited, and updates the account's last activity. A follow-up task can be scheduled in the same step; it becomes the next task of the deal or opportunity the activity is about.
- People can be added to an account and edited. A person added by hand is sourced "manual" and stays unverified until someone marks them verified. An address or domain on the suppression list cannot be added; the same email cannot be added twice to one account.
- Relationship tracking per person and per account is computed from the activities on every read, never stored: first and latest interaction, the number of interactions, days since contact, and the response status. A reply is an inbound message or a conversation (a connected call or a meeting); an outbound message or an unanswered call is an attempt; a note is neither. The status is not contacted, no reply yet, awaiting reply (they replied before, we have reached out since) or replied. Sentiment and relationship strength are not inferred.
- The follow-up engine flags four things, each computed from data: an **overdue follow-up** (an open task past its due date); **no next action** (an open opportunity without an owned, dated next action; won, lost and inactive deals no longer count); a **stale opportunity** (an open opportunity with no deal and nothing logged, completed or created for `VROS_STALE_OPPORTUNITY_DAYS`, default 14); an **inactive deal** (an open deal with no activity, completed task or stage move for `VROS_INACTIVE_DEAL_DAYS`, default 21). A deal is flagged instead of its opportunity once one is opened. Home lists the flags for everyone or just the user's own.

### Phase 3, slice 3.3: reporting (§13)

- Three dashboards over a chosen period (last 7, 30 or 90 days, last 12 months, or the year to date), every figure computed on request from the records themselves. Each figure carries the plain-English rule that produced it and, where a page can show the records behind it, a link there. A figure with nothing to count shows Unknown or an empty state, never zero standing in for "no data".
  - **Sales** (anyone who can read accounts, over the accounts they can see; optionally only their own work): new and qualified leads, new opportunities, deals opened, open and weighted pipeline, won and lost value, win rate, sales cycle (median days from opening a deal to winning it), activity logged by kind, overdue tasks and the follow-up flags.
  - **Lead intelligence** (anyone who reviews prospects or reads all accounts): companies researched, qualification and rejection rates, rejection reasons, lead quality (average priority score and bands of newly qualified leads), score distribution, top industries and countries, buying signals found by kind, opportunity types, data confidence and ICP performance (qualified leads, deals and wins by ICP score band).
  - **Management** (new permission `reports.team`: Admin, Founder, Sales Manager): the forecast, likely closes (open deals expected to close in the next 30 days), performance per salesperson, average won deal size, win rate, industries that convert, services that sell, lead sources that work and why deals are lost.
- The conversion funnel of §13 (Discovery → Qualified → Contacted → Reply → Meeting → Opportunity → Proposal → Won) follows the companies first researched in the period. A company counts at a step when it reached that step or a later one: contacted means a logged interaction, reply an inbound message or conversation, meeting a logged meeting, opportunity an opened deal, proposal a deal that reached the Proposal stage or beyond, won a won deal.
- Saved views: a saved view is a named link to a VROS page with its filters (a lead search, the pipeline, tasks, follow-ups or a dashboard). Anyone can save the page they are on as a personal view; Admins and others with `config.manage` can share one with the team. The team starts with My Hot Leads, Follow-ups Today, Stale Opportunities, UK SaaS Prospects, High Value Pipeline (open deals worth 10,000 or more, editable), New Buying Signals, Unassigned Leads and Deals Closing This Month.
- Not in this slice, because the data does not exist yet: clients with expansion potential and clients at risk (Phase 4), signals that predict wins (Phase 5 learning). They are left out of the dashboards rather than shown empty.

### Phase 3, slice 3.4: communication (§12, §12B)

- Each person connects their own mailbox over IMAP and SMTP (Gmail and Microsoft OAuth come later, behind the same `EmailProvider` interface). VROS never shares a mailbox. The password is encrypted at rest with a key derived from `VROS_SECRET_KEY` and never shown again. On connect, and on request, VROS signs in to both servers and checks the sending domain's MX, SPF, DKIM (with the selector the person enters) and DMARC, saying what to add when one fails.
- Sending one email is a person's click, and only after every pre-send check passes: sending switched on for VROS (`VROS_EMAIL_SENDING_ENABLED`, off by default), the mailbox connected and its owner's sending switch on, all four DNS checks passing, the daily cap not reached (default 20), the recipient having an email on a domain with a mail server, not on the suppression list (address, domain or account), not a competitor, not contacted by a colleague in the last 30 days, and, for a US company, a postal address configured. The checks are shown before writing.
- Every email carries the sender, the company and an opt-out line; US recipients also get the postal address. A sent email is stored, linked to the account, contact, and the deal or opportunity, and logged as an outbound activity on the timeline. A server failure is recorded as failed, with the reason.
- "Check for replies" reads new mail from the inbox (the last 14 days on first connection). Only mail from a known contact's address or replying to an email VROS sent is stored; nothing else enters VROS. A reply is logged as an inbound activity, so relationship tracking sees it. A reply that says "no thanks", "unsubscribe", "remove me" and the like suppresses the sender at once. A hard bounce (5.x.x) marks the email bounced and suppresses the address. Classifying other replies (interested, not now, referral) is left to slice 3.5.

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

As implemented (slice 1.6):
- The task title is the brief's recommended next action. It can be edited on approval or later.
- The due date is `VROS_TASK_DUE_BUSINESS_DAYS` business days after approval (default 2), with weekends skipped. Holidays are not yet known to the system.
- Priority follows the band: hot is urgent, high is high, everything else normal.
- Contacts are created only for people named on the company's own pages, with their stated title. The buying role comes from title keywords, or stays Unknown. Email and phone stay empty: they are never invented.

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
