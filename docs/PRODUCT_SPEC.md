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
- Moving a deal records the change (stage history, timeline, audit). Losing one requires a §13 lost reason. Winning one closes it; converting the account to a client is a separate, deliberate step (slice 4.1).
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

### Phase 3, slice 3.5: outreach (§12A, §12B)

- **Templates** for email and LinkedIn notes, with variables filled from the contact, the account and its lead brief: `{first_name}`, `{name}`, `{title}`, `{company}`, `{sender_name}`, `{why_now}`, `{problem}`, `{service}`, `{similar_project}`. A variable VROS has nothing for stays in the text, marked "to write", and an email cannot be sent until the person writes it in or removes it: nothing is invented. A follow-up email template has no subject and replies in the sequence's thread.
- **Sequences** mix email, LinkedIn and call steps, each a number of days after the one before. The default is §12B.4's: email, LinkedIn note (day 2), follow-up email (day 4), a call (day 7), a final note (day 11). Templates and sequences are managed by the new `outreach.manage` permission (Admin, Founder, Sales Manager); a sequence that people have gone through cannot change its steps (make a new one).
- **Enrolling** a contact shows every step as it would read for them and when it would fall due; "Approve sequence" is the approval. A contact can be in one live sequence at a time, and enrolling is refused for a suppressed contact (address, domain or account), a competitor, or someone without an email when the sequence sends email.
- **Per-step human action.** Nothing is sent automatically, ever: §12B.4's "approve once, then send on schedule" option is not built. Each due step waits in the enrolling person's **Outreach** queue (best prospects first): an email goes through the same pre-send checks as any email and is sent by their click; a LinkedIn note is copied, sent in their own browser, and recorded (sent, already connected, wrong person); a call is logged with its outcome. Any step can be skipped. LinkedIn notes are capped per person (`VROS_LINKEDIN_DAILY_LIMIT`, default 15; `VROS_LINKEDIN_WEEKLY_LIMIT`, default 80).
- **Auto-stop** (§12B.4), read from the records every time a sequence is looked at: a reply or a connected call, a logged meeting, a deal opened on the account, the contact suppressed (an opt-out reply, a hard bounce, a do-not-contact entry), or the contact removed. "Wrong person" ends it too. Automatic replies (out of office) are recorded but are not replies, so they stop nothing.
- Deferred: AI-drafted messages and AI reply classification (beyond opt-out, bounce and out of office), warm paths from LinkedIn connection exports, and send windows by recipient time zone.

### Phase 4, slice 4.1: client conversion and projects (§6, §14)

- **Convert to client** is offered on a won deal (the deal panel on the board, and the deal on the account). It keeps the same Account and everything on it: people, deals, opportunities, emails, activities, evidence and history are not copied or moved. The account becomes a Customer, gets a client-since date (the first conversion; a former client who comes back keeps it) and an account manager, and gets an owner if it had none. Competitor and suppressed accounts cannot become clients, and only a won deal converts.
- Converting may start a **project** for the work: its name (the deal's by default), service (the opportunity's by default), project owner (the account manager by default), start and target dates, planned milestones, and a kick-off task for the owner on the start date. One project per won deal; an existing client can start more projects from its Projects tab.
- **Projects** are light by design (VROS does not replace a project tool): the §6 statuses (Not Started, Planning, Active, At Risk, On Hold, Completed, Cancelled, set by a person), milestones that are reached or not, risks raised with a severity and resolved with a note, tasks (the ordinary task list, linked to the project), and notes. Marking a project completed records the date.
- An open project lists the plain facts someone should look at: no project owner, past its target date, overdue milestones, open high risks and overdue tasks. None is a judgement; how a client is doing overall (Green, Yellow, Red) is slice 4.2.
- Conversion, new projects, status changes, milestones reached and risks raised or resolved are on the account's timeline and in the audit log. Projects follow the account's visibility and move with it when accounts are merged.

### Phase 4, slice 4.2: client health and retention (§14)

- Every client is **Green, Yellow or Red**, worked out from the records on every read, and always shown with its reasons. **Red** when any of: an open project marked At Risk; a high risk open on an open project; a milestone 14 or more days overdue; no contact for 60 days; or negative feedback as the latest within 90 days. **Yellow** when any of: a project On Hold or past its target date; any overdue milestone or task; a medium risk open; no contact for 30 days; or three messages without a reply. **Green** otherwise. Contact is a logged call, meeting, email or message; the clock starts at the client-since date. The thresholds are settings (`VROS_CLIENT_QUIET_YELLOW_DAYS`, `VROS_CLIENT_QUIET_RED_DAYS`, `VROS_CLIENT_MILESTONE_RED_DAYS`, `VROS_CLIENT_FEEDBACK_DAYS`, `VROS_CLIENT_UNANSWERED_MESSAGES`).
- **Satisfaction is never guessed.** People record what a client said (positive, neutral or negative, with a note and the date); only that counts.
- **Retention engine:** each morning (06:00 UTC, run by the worker's embedded scheduler) VROS records any change of colour, with its reasons, as the client's health history and on the timeline. When a client turns Red it raises **Client risk detected** on the timeline and gives the account manager (or the owner) a follow-up task, unless one is already open. Negative feedback is checked at once rather than the next morning. Managers can run the check at any time. Nothing contacts the client.
- **Clients** page: every client, worst first, with its reasons, account manager, last contact and open projects; filtered by colour or to my clients. Red clients also appear on the Command Center, the management dashboard has a **Clients at risk** table, and the team has an **At-Risk Clients** saved view.
- **Ending a client relationship** makes the account a former client, keeping everything; open projects must be completed or cancelled first. Winning and converting a new deal makes them a client again.
- Expansion potential is shown beside health (slice 4.3) rather than changing its colour: health is about risk.

### Phase 4, slice 4.3: expansion and referrals (§11 land and expand, §14)

- **Expansion suggestions are evidence only.** Each is a problem research found on the client's own website (an opportunity candidate from one of its completed research runs), shown with the evidence it was found from and the confirmed services that answer it. A suggestion is left out when the client already has an opportunity in that category (open, won or lost) or someone has decided on it. A client with no research has no suggestions; nothing is inferred from industry, size or what similar clients bought.
- A person **opens** a suggestion as an opportunity (named "Expansion: <problem> for <client>", owned by the account manager, with the service when one answers it), then opens a deal from it, which goes into the Expansion pipeline as every client deal does. Or they **dismiss** it with a reason; it comes back only when a newer research run finds the problem again, and is marked as such. Both decisions are on the timeline and in the audit log, the opening with the evidence it rested on.
- The Clients page shows each client's waiting suggestions and filters to clients with expansion potential; the management dashboard has a **Clients with expansion potential** table and the team a **Clients With Expansion Opportunities** saved view.
- **Referrals** record who referred a company (an account and one of its people, or just a name), how they know Verkies, the referred company and its website, the date, a status (received, contacted, declined) and notes. The referred company is matched to its account by website whenever it is read, so a referral logged before the company is in VROS links up later. **Converted** means a deal on the referred company was won on or after the referral date; **revenue** is those deals' values per currency, with deals without a value counted separately. Referrals show on both accounts, on a Referrals page, and in a **Referrals** table on the management dashboard. A referral given by an account is visible to whoever can see that account.

### Phase 4, slice 4.4: documents (§14)

- Proposals, requirements, briefs, contracts, statements of work, meeting notes, screenshots and project documents are uploaded to an account and, when they belong to one, linked to its deal, opportunity or project. They are listed on the account's **Documents** tab and on the project page, newest first, with what they are, their size, who added them and when.
- Accepted files: PDF, Word, Excel, PowerPoint, PNG, JPEG, WebP, text, Markdown and CSV, up to 10 MB (`VROS_DOCUMENT_MAX_BYTES`). What a file is comes from its own bytes and must match its name; anything else is refused with the reason. Downloads only: VROS never opens a file in the page (`SECURITY.md` §4).
- Uploads and removals are on the timeline and in the audit log. Documents follow the account's visibility and move with it when accounts merge. The files are part of the nightly backup.

### Phase 5, slice 5.1: feedback and outcomes (§13, §15)

- **Salesperson feedback:** Good Lead, Bad Lead, Contacted, Meeting Booked, Proposal Sent, Won, Lost, Wrong Buyer, Wrong Service, Not Now, Not ICP, Duplicate, Competitor, Opportunity Confirmed, Opportunity Incorrect. Given on the account (optionally about one of its opportunities) with a reason, kept with who gave it and when, and on the timeline. It is stored for the learning engine and changes nothing by itself.
- **Deal outcomes:** when a deal is won or lost, VROS records, in the same transaction, what was true at that moment (§13 won-deal data): the service and opportunity type, industry, company size, country, lead source, the buyer role of the person the deal was worked with most, the sales cycle (days as a deal and from qualification), the value, the dated buying signals of the six months before, the scores when the lead was first scored and at the close, and the most similar Verkies reference project. Facts VROS does not have are stored as Unknown. Reopening the deal marks the record superseded; closing it again writes a new one, so history is never rewritten. The deal panel shows the record under "When it was won/lost".
- Deals that closed before this slice get their record from `python -m app.cli backfill-outcomes`, marked as captured late (the facts are as of the backfill).

### Phase 5, slice 5.2: win/loss analysis (§13, §15)

- A **Learning** page reads the recorded deal outcomes (slice 5.1) for the accounts the person can see, over the last 6, 12 or 24 months or all time: the overall win rate, value won and days to win, then the same by service, opportunity type, industry, company size, country, lead source, buyer role and priority when first scored.
- **Buying signals**: for each signal seen in the six months before a close, the win rate of deals with it against deals without it.
- **Why deals were lost** (the §13 reasons), and how deals did on accounts that had each kind of salesperson feedback **before** the close (feedback given after says nothing about how the lead looked).
- Every figure shows the deals it rests on. A group with fewer than `VROS_LEARNING_MIN_SAMPLE` (default 5) closed deals gets no win rate and is marked too few to learn from. Unknown is its own group and is never merged into another. Outcomes recorded late (backfilled) are counted and flagged.
- This is description, not prediction: nothing here changes a score. Proposing changes from it is slice 5.3, and a person activates them.

### Phase 5, slice 5.3: learned proposals (§15; SCORING_SPEC.md §7)

- On the Learning page, admins can ask VROS to **propose scoring weights** or **ICP industry tiers** from every won and lost deal. Each proposal lists every change with its evidence ("won deals first scored 87 on average against 32 for lost, 5 won, 5 lost"; "won 5 of 5 against 50% across all industries") and the config version it was made against.
- Proposals are cautious by design: none from fewer than the minimum won and lost deals, no weight moves by more than a quarter of itself, an industry moves one tier at most (SCORING_SPEC.md §7 has the exact rules), and the same data always gives the same proposal.
- **Nothing changes until an admin activates a proposal.** Activating saves a new config version (validated and audited exactly like an edit in Settings) and is refused if the configuration changed in the meantime. Proposals can be dismissed with a reason, and the new version can be edited in Settings at any time: human override is kept. Managers can see proposals; only admins make and activate them.
- Existing scores are not recalculated by activating; new research uses the new version, and every score records the version it used.

### Phase 5, slice 5.4: similarity learning (§11, §15)

- **Won clients become similarity references** alongside Verkies' reference projects, so client similarity reflects who actually buys. A client's profile comes from the outcomes of the deals Verkies won with it (slice 5.1): the industry when it was won, the services sold and the problems those deals answered.
- Like a reference project, a client is compared only when its profile is complete (industry known, and a service or a problem); otherwise it is skipped. A lost deal makes no reference, and a prospect is never compared with its own account.
- The brief names a matching client as a client ("Acme Legal (a Verkies client): similar because same industry"), never as a portfolio case study. With no complete project or client profile, similarity stays **Unknown**.
- Similarity results record which reference they were against: a reference project or a client account, exactly one.

### Phase 6, slice 6.1: watchlists and signal monitoring (§15)

- Anyone who can see an account can **watch** it (Watch on the account page). Watched accounts are re-checked every morning at 05:00 UTC by the worker's scheduler, and **Check now** queues a check at once.
- A check re-reads the sources the account's latest research found: the job boards and news feeds its own website links to (fresh copies, never the crawl cache) and its Companies House record and filings. It never crawls the whole site, never contacts anyone, and an account with no completed research has nothing to check.
- What a check reads is stored as a **monitoring check**: a research run of kind `monitor` on the account, with review not required. It is never listed with research, never in the review queue and never counted in the research reports, but its signals count like any others for ranking, timing, outcomes and the learning engine.
- A signal VROS had not seen before for that account (the same posting, story or filing read again is recognised) becomes an **alert** with its source, and a line on the account's timeline. A source that fails is recorded on the check, never treated as "nothing new".
- The **Monitoring** page lists alerts to review (or all), for the accounts you watch or everyone's, and the watched accounts with when each was last checked and how many alerts wait. The account page shows its alerts while you watch it.

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
