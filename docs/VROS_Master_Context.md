# Verkies Revenue Operating System — Master Context

Oct 8, 2026 · @Muhammad Awais Azam

## 1. About this document

This is the single source of truth for building the Verkies Revenue Operating System (VROS). Hand it to Claude Code as product context before any code is written.

It merges two earlier versions:

- **The full PRD (v1.0)**, which has the detailed field lists, roles, ICP tiers, target cities, metrics and loss reasons.
- **The Claude Code context brief**, which adds the free-first tool rules, the conversion funnel, the four-layer definition and the build instructions.

Where the two overlap, the more detailed wording is kept. Section 23 holds the instructions Claude Code must follow first.

| Field | Value |
| --- | --- |
| Product | Verkies Revenue Operating System (VROS) |
| Company | Verkies Private Limited |
| Version | 1.1 (merged master context) |
| Status | Product definition / build specification |
| Primary objective | An enterprise-grade, intelligence-first revenue platform covering prospect intelligence, qualification, CRM, sales pipeline, client management, project lifecycle, retention, expansion and learning |

## 2. Vision, objectives and North-Star metric

VROS is a unified platform for Verkies to identify, research, qualify, prioritize, manage, convert and retain high-value prospects and clients. It should become Verkies' central revenue operating system.

**It is not** a generic lead scraper, an Apollo clone, a contact database, a generic CRM, a mass cold-email platform or a directory of companies. It combines lead intelligence, ICP qualification, opportunity detection, CRM, sales pipeline, client lifecycle, expansion and learning in one system.

**The core question:** "Which companies should Verkies contact, why should Verkies contact them, who should Verkies speak to, what should Verkies sell them, and what should happen next?"

**The full lifecycle:** Discover → Research → Verify → Enrich → Qualify → Score → Reject → Prioritize → Contact → Engage → Opportunity → Deal → Won/Lost → Client → Project → Retain → Expand → Refer → Learn.

The complete history of an account is kept through every stage. The system should keep improving its recommendations from Verkies' own sales and client outcomes.

### Business objectives

VROS must:

1. Increase qualified-lead precision.
2. Reduce time spent researching bad prospects.
3. Identify genuine commercial opportunities.
4. Identify relevant decision makers.
5. Explain why Verkies should contact each prospect.
6. Recommend the most appropriate Verkies service.
7. Provide evidence for every important intelligence claim.
8. Manage the entire sales pipeline.
9. Manage customer relationships after conversion.
10. Identify upsell and cross-sell opportunities.
11. Track client health and retention risks.
12. Learn from won and lost opportunities.
13. Continuously improve ICP and scoring accuracy.

### North-Star metric: Qualified Lead Precision

The percentage of recommended prospects that a Verkies salesperson agrees are worth contacting.

| Stage | Target |
| --- | --- |
| Initial | at least 80% |
| Mature | at least 90% |

Optimize for quality over quantity. 1,000 irrelevant leads are worse than 30 highly relevant opportunities.

## 3. Core product principles

Every feature must measurably improve at least one of these: prospect quality, sales productivity, pipeline visibility, conversion, retention, expansion or revenue intelligence.

1. **Quality over quantity.** Irrelevant leads are harmful.
2. **Evidence first.** No important claim is shown without evidence. Every intelligence observation stores the source URL, source domain, collection date and time, source publication date when available, evidence text, evidence type and confidence score.
3. **No hallucinations.** The platform never invents company information, funding, employee counts, technology, decision makers, job titles, problems, revenue, client history, business activity, buying signals, quotes or case-study claims. Unverified information is shown as **Unknown**.
4. **Opportunity over observation.** Technical findings are turned into business value.
   - Bad: "The company uses WordPress."
   - Good: "The company's enquiry journey routes users to a generic contact page despite offering high-value services. A structured conversion and lead-management workflow may be a relevant Verkies opportunity."
5. **Rejection is a first-class operation.** Low-quality prospects are rejected aggressively. Rejected prospects stay searchable for audit but never clutter the sales queue. Rejection reasons:
   - no commercial opportunity
   - wrong ICP
   - inactive company
   - duplicate
   - competitor
   - insufficient evidence
   - no relevant Verkies service
   - no reachable buyer
   - hobby or personal project
   - student or freelancer
   - clearly unsuitable company size
   - irrelevant industry
   - existing solution appears sufficient
   - suppressed account
6. **The Account is the permanent central entity.**
7. **Intelligence and CRM are one unified system.**
8. **No uncontrolled spam automation.**
9. **Paid tools are not required for the core product.**

## 4. Target users

Six user types drive the requirements. The matching system roles are in Section 17.

| User | Needs |
| --- | --- |
| Founder / Management | Revenue overview, pipeline, forecast, salesperson performance, high-value opportunities, client health, expansion opportunities, intelligence trends |
| Sales Manager | Lead queue, team pipeline, assignments, follow-ups, conversion metrics, lead quality, sales activity, performance monitoring |
| Salesperson | Qualified leads, buyer information, opportunity explanation, evidence, recommended service, relevant case study, sales angle, next action, follow-up reminders |
| Researcher | Discovery, company research, website analysis, evidence collection, contact research, verification, enrichment |
| Project Manager | Client accounts, projects, milestones, tasks, deadlines, risks, communication history |
| Viewer | Read-only access to permitted records |

## 5. Ideal customer profile (ICP)

The ICP is encoded as a configurable qualification engine. Industry or geography alone never qualifies a lead.

### Master ICP

A commercially active startup, scale-up, growth-oriented or established business with a demonstrable need for:

- software or product development, MVP development, SaaS
- web or mobile applications, marketplaces
- internal systems, CRM, workflow automation, digital transformation
- website development or rebuild
- SEO, conversion optimization, growth marketing

It must also show evidence of budget potential, urgency, growth, operational pain, product development, hiring, funding, expansion, technical problems or digital growth opportunities. A relevant decision maker must be reasonably identifiable.

### Industry priority

| Tier | Industries | Rule |
| --- | --- | --- |
| S (highest) | SaaS, AI startups, AI SaaS, FinTech, HealthTech, PropTech, EdTech, MarTech, marketplaces, software companies, funded startups, product startups | Standard evidence |
| A | Immigration, legal, recruitment, accounting, consulting, healthcare, logistics, travel technology, real estate, professional services, e-commerce platforms, education technology | Standard evidence |
| B | Construction, automotive, hospitality, restaurants, retail, fitness, beauty, local services | Needs stronger evidence |

### Geographic priority

Geography influences scoring but never overrides opportunity evidence.

| Priority | Region | Focus areas |
| --- | --- | --- |
| 1 | United Kingdom | London, Manchester, Birmingham, Cambridge, Oxford, Bristol, Edinburgh |
| 2 | United States | New York, San Francisco Bay Area, Austin, Boston, Seattle, Los Angeles, Chicago, Miami |
| 3 | Canada | Country-wide |
| 4 | Australia | Country-wide |
| 5 | Western Europe | Netherlands, Germany, France, Ireland, Switzerland, Sweden, Denmark |
| 6 | UAE | Dubai, Abu Dhabi |

### Negative ICP

Reject or deprioritize:

- inactive or closed companies, parked domains
- personal or hobby projects
- students, freelancers, job seekers
- influencers and personal brands
- irrelevant organizations, competitors, duplicates
- companies with no identifiable commercial opportunity
- companies with no plausible Verkies service fit
- companies with insufficient evidence
- companies with no plausible buyer
- clearly satisfied customers where no opportunity exists

### Agencies

Agencies never enter the standard sales queue automatically. Classify each as a competitor, potential partner, referral partner, white-label partner or subcontracting opportunity.

## 6. Account-centric architecture and data objects

The **Account** is the permanent record. Everything else is a state, relationship, activity or commercial event attached to it. A company never becomes a disconnected "client record" after it converts, and no history is lost when its lifecycle state changes.

**Lifecycle states:** Prospect → Qualified Prospect → Opportunity → Customer → Former Customer.

**Other account types:** Partner, Competitor, Suppressed.

One Account can have many contacts, leads, opportunities, deals, projects, campaigns, activities, communications, proposals, intelligence reports and expansion opportunities.

### Core objects and fields

| Object | What it is | Fields |
| --- | --- | --- |
| Account | The permanent company record | ID, company name, legal name, website, domains, industry, sub-industry, business model, description, headquarters, locations, country, company size, estimated revenue (when verified), technologies, account type, account status, owner, source, ICP score, opportunity score, intent score, buyer confidence, data confidence, service fit, commercial potential, client similarity, priority score, created date, updated date, last activity, next activity |
| Contact | A person at an Account | Name, title, department, email, phone, profile URL, source, confidence, decision-maker role, account, notes, relationship state, verification status |
| Lead | A sales-relevant qualification event on an Account | Account, source, campaign, owner, ICP score, opportunity score, intent score, buyer confidence, data confidence, service fit, priority, status, qualification date, rejection reason, next action, created date, updated date |
| Opportunity | A specific commercial problem or potential project | Account, opportunity name, problem, opportunity type, service, estimated value, currency, probability, expected close, stage, source, buying signals, pain points, requirements, decision makers, evidence, notes, owner, next action |
| Deal | A commercial agreement in a pipeline | Opportunity, account, deal value, currency, pipeline, stage, probability, expected close, actual close, owner, source, won/lost status, won reason, lost reason |
| Project | Delivery work created after a deal is won | Account, deal, project name, service, project owner, account manager, start date, target completion, actual completion, status, milestones, tasks, risks, documents, notes |
| Task | A piece of work with an owner | Linked account, contact, lead, opportunity, deal or project; title, description, owner, due date, priority, status, recurring schedule |
| Evidence | The source behind a claim | Source URL, source domain, collected at, published at (when available), evidence text, evidence type, confidence |

**Contact decision-maker roles:** Economic Buyer, Decision Maker, Technical Buyer, Product Buyer, Marketing Buyer, Operations Buyer, Champion, Influencer, User, Procurement, Blocker.

**Project statuses:** Not Started, Planning, Active, At Risk, On Hold, Completed, Cancelled.

Other CRM objects (Activity, Meeting, Communication, Proposal, Document, Referral, Buying Signal) are described in Sections 12–15.

## 7. Core modules

VROS has 38 modules. They are grouped here by the four product layers in Section 22, plus a platform layer.

| Layer | Modules |
| --- | --- |
| Intelligence | Account Management, Company Intelligence, Lead Discovery, Lead Qualification, Opportunity Detection, Decision-Maker Intelligence, Buying-Signal Detection, Website Intelligence, Technology Intelligence, SEO Intelligence, Conversion Intelligence, Product Intelligence, Similar Client Intelligence, Service Matching, Lead Scoring, Monitoring |
| CRM | CRM, Contacts, Activities, Tasks, Opportunities, Deals, Sales Pipelines, Communication History, Proposal Management |
| Client management | Client Management, Project Management, Client Health, Retention, Expansion, Referral Management |
| Learning | Feedback, Win/Loss Analysis, Learning Engine, Reporting |
| Platform | Notifications, Administration, Audit Logs |

## 8. Intelligence engine

The engine analyses public company information. Every finding must be connected to a commercial opportunity, and technology alone never qualifies a lead.

| Area | What to analyse |
| --- | --- |
| Website | HTTPS and SSL, redirects, mobile viewport, loading performance, page size, performance metrics where available, broken links, sitemap, robots.txt, canonical tags, structured data, accessibility indicators, security headers, outdated technologies, content structure |
| SEO | Title tags, meta descriptions, H1/H2, canonical, schema, sitemap, robots, indexability, internal and external links, alt attributes, content depth, content freshness, service pages, location pages, search-intent coverage, topical-authority indicators |
| Conversion | Primary and secondary CTA, phone, email, forms, quote request, booking, WhatsApp, chat, testimonials, reviews, trust badges, case studies, pricing, social proof, newsletter, lead capture. Decide whether the customer journey gives a credible conversion path. |
| Product | Login, signup, dashboard, portal, booking system, marketplace, calculator, search, account creation, payment, subscriptions, SaaS indicators, API indicators, product workflows |
| Technology | Where detectable: WordPress, WooCommerce, Shopify, Wix, Squarespace, Webflow, Elementor, React, Next.js, Vue, Angular, Laravel, PHP, Node.js, Python, Rails, Drupal, Magento, custom applications |

## 9. Opportunities, buying signals and decision makers

### Opportunity detection

This is one of the most important modules. It turns verified observations into potential commercial opportunities.

- **Observation:** the website has a generic contact form.
- **Opportunity:** the company sells high-value services but has no structured lead intake. Verkies could build a structured enquiry, qualification, appointment, CRM and client-management workflow.

**Opportunity categories:** MVP development, SaaS development, product rebuild, technical rescue, application modernization, website rebuild, mobile application, marketplace, CRM, client portal, workflow automation, internal tools, digital transformation, booking system, document workflow, customer onboarding, payment workflow, SEO, content strategy, conversion optimization, paid acquisition, growth marketing, analytics, integrations, ongoing product support.

Never list every Verkies service for every company. Recommend the most relevant one, plus secondary or expansion services only when evidence supports them.

### Buying signals

Every signal stores its type, source, URL, date, evidence and confidence.

| Strength | Signals |
| --- | --- |
| Very strong | Funding, product launch, developer hiring, CTO hiring, product hiring, announced development project, agency or technical-partner search, developer replacement, technical problem, MVP announcement, platform rebuild |
| Strong | New CEO, new CTO, new product leader, acquisition, geographic expansion, new service, new market |
| Medium | Website redesign, increased hiring, increased content, product updates, new marketing campaign |

### Decision-maker intelligence

Identify buyers only where they are publicly and reliably available. Never invent a person, title, contact detail or relationship.

| Area | Roles |
| --- | --- |
| Primary | Founder, CEO |
| Technical | CTO, VP Engineering, Head of Engineering |
| Product | Head of Product, Product Manager |
| Growth | CMO, Head of Growth, Marketing Director |
| Operations | COO, Operations Director |

## 10. Scoring and qualification

VROS keeps ten independently explainable scores from 0 to 100 and combines them into a **Verkies Priority Score**. All weights and thresholds are configurable by administrators; none are hard-coded.

**Score dimensions:** ICP Fit, Opportunity, Intent, Buyer Confidence, Data Confidence, Service Fit, Timing, Commercial Potential, Client Similarity, Evidence Strength.

### Qualification rules

A prospect should generally have:

- meaningful ICP fit
- an identifiable commercial opportunity
- sufficient evidence
- reasonable confidence in the account data
- at least one strong buying signal, or several verified problem signals
- a plausible Verkies service fit

### Priority bands (default)

| Priority Score | Band |
| --- | --- |
| 90–100 | Hot — contact now |
| 75–89 | High priority |
| 60–74 | Qualified — research further |
| 40–59 | Monitor |
| Below 40 | Reject / suppress |

## 11. Lead brief, similar clients and service matching

Every recommended prospect gets a structured brief that a salesperson can understand within seconds.

### Lead brief fields

Company · Priority · ICP Fit · Opportunity · Intent · Buyer Confidence · Data Confidence · Company Overview · Why Verkies? · Why Now? · Problem Detected · Recommended Service · Best Buyer · Similar Verkies Client/Project · Sales Angle · Risks · Evidence · Recommended Next Action

### Why Verkies?

A specific explanation built from verified company characteristics, the detected opportunity, the relevant Verkies capability, a similar client or project, buying signals and timing.

- Not allowed: "Verkies can help your business grow."
- Expected: "The company appears to be expanding its service operation while relying on manual enquiry and onboarding processes. This resembles Verkies' work on workflow-heavy professional-service businesses, making a CRM/client-portal automation project a plausible fit."

### Why Now?

Urgency drawn from evidence: recent funding, hiring, product launch, expansion, technical issue, website redesign, new leadership, operational growth, new market or new product.

### Lead card

Each card shows: Company, Priority Score, Why Fit, Opportunity, Why Now, Recommended Service, Buyer, Evidence, Similar Verkies Work, Next Action. Actions: Research, Contact, Approve, Reject.

### Similar client engine

Compare each prospect with Verkies' previous work. Initial reference archetypes: Wesbridge Associates, Oerno, ShiftRow, THEOO Property, LumiNexis TBG and Ask iDeer, where data is available.

- Similarity considers industry, business model, problem, service, technology, operational workflow, growth stage, buyer type and project characteristics.
- Compare business problems, not just industries.
- Output a Similarity Score (0–100) and a short "Similar because…" explanation.

### Service matching

Recommend at most three services, each only when evidence supports it.

| Slot | Meaning | Example |
| --- | --- | --- |
| Primary | Most relevant immediate opportunity | CRM / internal platform |
| Secondary | Possible additional opportunity | Website rebuild |
| Expansion | Likely future opportunity | SEO + growth retainer |

### Land and expand

Model the path Entry Service → Expansion 1 → Expansion 2 → Expansion 3, for example website rebuild → CRM → client portal → SEO → growth marketing. Create expansion opportunities only when evidence supports them.

## 12. Native CRM

The CRM is part of the same product, not a separate application, and is deeply connected to the intelligence layer. It manages accounts, contacts, leads, opportunities, deals, activities, tasks, meetings, communications, proposals, projects, clients and expansion. The same Account persists from prospect through client and expansion.

### Sales pipelines (defaults, all configurable)

| Pipeline | Stages |
| --- | --- |
| New Business | New → Qualified → Researching → Contacted → Engaged → Discovery Call → Qualified Opportunity → Proposal → Negotiation → Verbal Agreement → Won / Lost / Nurture |
| Existing Client Expansion | Existing Client → Opportunity Detected → Discussing → Discovery → Proposal → Negotiation → Won / Lost |
| Partnership | Identified → Researched → Contacted → Conversation → Potential Partnership → Active Partner → Inactive |

### Kanban card

Company, opportunity, deal value, owner, priority, next task, last activity, days in stage, probability.

### Account 360

One unified page per account, combining business intelligence, sales history, client history, project history and future opportunities. Tabs:

Overview · Intelligence · Contacts · Leads · Opportunities · Deals · Activities · Emails · Calls · Meetings · Tasks · Notes · Documents · Projects · Monitoring · Timeline · Related Accounts · Audit History

### Unified timeline

Everything tied to the account appears in date order: company discovered, website analysed, lead qualified, buying signal detected, email sent, call completed, meeting booked, proposal created, deal stage changed, deal won, project created, milestone completed, expansion opportunity detected.

### Activities

Call, email, WhatsApp or manual message, LinkedIn or manual activity, meeting, note, task, follow-up, proposal, contract, status change, research, website analysis, AI insight, buying signal. The system never spams prospects automatically.

### Tasks

Tasks can belong to an account, contact, lead, opportunity, deal or project. Fields are listed in Section 6.

### Next action engine

Every active opportunity must have a next action, a responsible owner and a due date. If any is missing, flag it prominently as "Opportunity requires attention."

### Follow-up engine

- **Track:** last contact, days since contact, next follow-up, attempts, response status.
- **Flag:** overdue follow-up, stale opportunity, no next action, inactive deal.
- AI may recommend follow-ups but never sends them without explicit configuration and appropriate consent and compliance.

### Contact relationship management

Track first interaction, latest interaction, number of interactions, response status, sentiment (where explicitly supported), relationship strength, decision-maker role and notes.

### Communication

- Provider abstraction for Gmail, Outlook, SMTP, IMAP, calendar and future providers.
- Emails are linked to the Account, Contact, Opportunity and Deal.
- The core CRM works without paid APIs.
- AI may draft messages, but sending requires explicit configuration and compliance controls.

## 12A. LinkedIn channel

LinkedIn is a first-class outreach and research channel in VROS, run as **human-in-the-loop**. The system prepares who to approach, why, and what to say; the salesperson does every LinkedIn action in their own browser; VROS records and learns from the result. Nothing is scraped and nothing is sent automatically, which keeps every account safe from LinkedIn restrictions and costs nothing.

### What VROS does

1. **Finds the right person to look up.** For each qualified Account, the lead brief shows the target buyer roles (Section 9) and one-click **LinkedIn search links** built from the company name and role keywords, e.g. people search for "CTO" OR "Head of Engineering" at that company. The link just opens LinkedIn in the user's browser.
2. **Captures the profile without scraping.** The salesperson pastes the profile URL and, optionally, the profile text they can see. The AI extracts name, title, tenure and past roles into the Contact, tagged source "LinkedIn (manual)" with the capture date. Facts not in the pasted text stay Unknown.
3. **Maps your existing network.** Each team member uploads LinkedIn's own free data export (Settings → Data privacy → Get a copy of your data → Connections). VROS matches first-degree connections to Accounts and flags **warm paths**: "Awais is connected to the COO." A warm path raises Buyer Confidence and becomes the recommended first move.
4. **Drafts the outreach.** The AI writes a short connection note, a first message after acceptance, a follow-up, and a comment idea for the prospect's recent post, all grounded in the lead brief's Why Verkies and Why Now. The salesperson edits and sends them.
5. **Tracks every step** as CRM activities on the Account timeline.

### Assisted mode: the daily LinkedIn queue

VROS automates everything except the click on LinkedIn itself. Target: under one minute per prospect.

1. **Daily queue.** Each morning VROS builds a LinkedIn queue per salesperson (default 10–15 people, configurable), ranked by Priority Score, warm paths and due sequence steps. It never exceeds the user's weekly connection-request cap.
2. **Open.** One click opens the next prospect's LinkedIn profile (or the search link, if no profile is saved yet) in the user's normal browser, and copies the drafted note or message to the clipboard.
3. **Send.** The salesperson reviews the draft, pastes it, edits if needed, and clicks send on LinkedIn.
4. **Log.** Back in VROS, one button marks the outcome (Sent, Skipped, Wrong person, Already connected). VROS logs the activity, advances the sequence, schedules the next step as a task, and loads the next prospect.
5. **Replies.** When a prospect replies, the salesperson clicks Reply received and can paste the reply. The AI classifies it (interested / not now / not relevant / referral) and drafts a response, and an interested reply raises the Lead to the Engaged stage.

The queue screen shows progress (e.g. 7 of 12 done), the weekly request count against the cap, and a short Why Now line for the current prospect, so the salesperson never switches context to look things up.

Keyboard shortcuts drive the queue (open, mark sent, skip, next), so the whole loop runs without a mouse.

### LinkedIn activities

Profile viewed · Post engaged (like or comment) · Connection request sent · Connection accepted · Message sent · Reply received · InMail sent · Meeting booked from LinkedIn. Each takes one click from the Account or Contact page.

### Default LinkedIn sequence (configurable)

1. Day 0: view profile, engage with a recent post if relevant.
2. Day 1–2: connection request with a personalised note.
3. On acceptance: first message (value-led, no pitch dump).
4. +4 days without reply: one follow-up.
5. +7 days without reply: switch channel to email, or set the lead to Nurture.

The Next Action engine (Section 12) creates each step as a task for the owner.

### Signals logged from LinkedIn

Salespeople can log what they see as dated buying signals with the post or profile URL as evidence: job change (new CTO, new Head of Product), hiring post, funding announcement, product launch, expansion post. These feed scoring like any other signal (Section 9).

### Data fields added

| Object | New fields |
| --- | --- |
| Account | LinkedIn company URL, LinkedIn employee range (manual, dated) |
| Contact | LinkedIn profile URL, connection status (not connected / pending / connected), connected via (team member), connected date, last LinkedIn touch |
| Activity | Channel = LinkedIn, activity type (list above) |

### LinkedIn metrics

Connection acceptance rate, reply rate, meetings from LinkedIn, warm-path conversion versus cold, and best-performing note and message templates. These feed the learning engine (Section 15).

### Guardrails

- No scraping, no browser-automation or auto-connect tools, and no stored LinkedIn passwords or session cookies.
- Keep connection requests within LinkedIn's weekly limits; VROS shows each user's weekly count.
- Sales Navigator is optional. If Verkies buys it later, its saved-lead URLs can be pasted in the same way, with no integration required.

## 12B. Built-in outreach (email + LinkedIn)

Outreach runs inside VROS: the salesperson reviews an AI-drafted email built from the lead brief and sends it with one click from their own mailbox. Replies, follow-ups, meetings and opt-outs flow back automatically. It uses free APIs only and is built in Phase 3.

### 1. Connect a mailbox

- **Gmail / Google Workspace** via the Gmail API (OAuth), or **Outlook / Microsoft 365** via Microsoft Graph (OAuth). SMTP + IMAP as a fallback.
- Each salesperson sends from their own address; VROS never shares one mailbox across people.
- On connect, VROS checks the domain's SPF, DKIM and DMARC records and shows what to fix before sending is allowed.

### 2. Draft from the lead brief

- The AI writes subject and body from Why Verkies, Why Now, Problem Detected, the similar Verkies project and the evidence (Section 11). Every claim must trace to evidence; no invented facts or compliments.
- Plain text, short (target 60–120 words), one clear ask.
- Default call to action is the sender's booking link (e.g. "30 min with Rana"); the link is set per user in Settings.
- A template library (by service, industry and signal) gives the AI a starting point; templates use variables such as `{first_name}`, `{company}`, `{why_now}`, `{similar_project}`.

### 3. One-click send

- **Single email:** from the Account, Lead or Contact page, open the draft, edit if needed, click **Send**. VROS sends through the user's mailbox, stores the message on the timeline and links it to Account, Contact, Opportunity and Deal.
- **Outreach queue:** a daily review screen (like the LinkedIn queue in 12A) lists drafted emails ranked by priority. The salesperson reviews each and clicks Send, Edit or Skip; keyboard shortcuts move through the list.
- **Send window:** emails go out in the recipient's business hours (by account country), with small random spacing, within the mailbox's daily cap.

### 4. Sequences (multichannel)

A sequence mixes email, LinkedIn and call steps. Default:

1. Day 0: email 1 (personalised, from the lead brief).
2. Day 1–2: LinkedIn connection request (assisted, Section 12A).
3. Day 4: email 2, a short follow-up in the same thread.
4. Day 7: LinkedIn message or call task.
5. Day 11: email 3, a final short note; then Nurture.

- **Approve once:** when enrolling a contact, the salesperson reviews all steps and clicks **Approve sequence**. Approved follow-ups then send on schedule. This is the explicit configuration the PRD requires; an admin can switch it off so every step needs its own click.
- **Auto-stop** on any reply, meeting booked, bounce, opt-out, or when the contact's account becomes an Opportunity.

### 5. Replies and meetings come back automatically

- VROS reads replies through the Gmail or Graph API (or IMAP), matches them to the thread, logs them on the timeline and stops the sequence.
- The AI classifies each reply: interested, not now, not relevant, referral, out of office, opt-out, bounce. Interested replies move the Lead to Engaged and create a task to respond within 24 hours; out-of-office pauses the sequence until the return date.
- **Unified inbox:** one screen for all email and LinkedIn replies across the team, with AI-drafted responses ready to send in one click.
- Booked meetings are detected from the user's Google or Microsoft calendar; VROS logs a Meeting, moves the deal to Discovery Call and attaches the lead brief to the meeting.

### 6. Deliverability (protects Verkies' domain)

- **Daily caps per mailbox,** starting low for new mailboxes and ramping up (default start 20 per day, configurable).
- **Bounce handling:** a hard bounce marks the email invalid and stops all sequences to it.
- **Pre-send checks:** MX record exists, the contact is not suppressed, not already in an active sequence, and not contacted by a colleague in the last 30 days.
- **No open-tracking pixels by default** (they hurt deliverability and accuracy); replies and meetings are the success measures. Link-click tracking is optional and off by default.
- Optional: a separate sending subdomain (e.g. hello.verkies.com) so outreach never affects the main domain.

### 7. Compliance

- Every email identifies the sender and company and includes a simple opt-out line ("Reply 'no thanks' and I won't contact you again"). Opt-outs are honoured instantly.
- **Global suppression list** covering opted-out people, domains, existing clients (unless in the expansion pipeline), competitors and do-not-contact accounts.
- Contact data keeps its source and collection date, and a lawful-basis note (B2B legitimate interest) for UK GDPR and PECR.
- For US recipients, a postal-address footer is added automatically (CAN-SPAM); the footer is configurable by region.
- Bulk "send to everyone" does not exist. Every first email is reviewed by a person.

### 8. Data objects added

| Object | Fields |
| --- | --- |
| Mailbox | Owner, provider, address, auth status, SPF/DKIM/DMARC status, daily cap, warm-up stage |
| Template | Name, channel, service, industry, signal, subject, body, variables, performance |
| Sequence | Name, steps (channel, delay, template), stop rules, owner |
| Enrollment | Contact, account, sequence, current step, status, approved by, approved at, next send at |
| Message | Channel, direction (out/in), thread ID, subject, body, sent/received at, status (sent, bounced, replied), reply class |
| Suppression | Email or domain, reason, added by, added at |

### 9. Outreach metrics

Sent, bounced, reply rate, positive reply rate, meetings booked, opt-out rate, and time to first reply, by template, sequence step, service, industry, signal and salesperson. Results feed the learning engine (Section 15), so the AI learns which angles win meetings.

## 13. Forecasting, win/loss analysis and reporting

### Forecasting

Management sees total pipeline, weighted pipeline, forecast, pipeline by month, quarter and year, won revenue, lost revenue and expected revenue.

### Conversion funnel

Track conversion at each step: Discovery → Qualified → Contacted → Reply → Meeting → Opportunity → Proposal → Won.

### Lost-deal reasons

Price, no budget, timing, competitor, internal development, freelancer, another agency, cancelled, no decision, lost contact, requirements changed, poor fit, other.

### Won-deal data

Capture service, industry, company size, geography, buying signal, buyer role, sales cycle, deal value, source, original lead scores, relevant case study and opportunity type. This feeds the learning engine.

### Dashboards

| Dashboard | Shows |
| --- | --- |
| Sales | New leads, qualified leads, opportunities, pipeline, weighted pipeline, won revenue, lost revenue, conversion rate, sales cycle, follow-ups, overdue activities |
| Lead intelligence | Lead quality, qualification rate, rejection rate, score distribution, top industries, top geographies, top signals, opportunity types, data confidence, ICP performance |
| Management | Pipeline, likely closes, salesperson performance, average deal size, win rate, industries that convert, services that sell, lead sources that work, signals that predict wins, why deals are lost, clients with expansion potential, clients at risk |

### Saved views

My Hot Leads · Follow-ups Today · Stale Opportunities · UK SaaS Prospects · High Value Pipeline · Clients With Expansion Opportunities · At-Risk Clients · New Buying Signals · Unassigned Leads · Deals Closing This Month

### Notifications (configurable)

High-priority lead, new buying signal, due task, overdue task, email reply, meeting, proposal, deal change, client risk, expansion opportunity, monitoring alert.

## 14. Client lifecycle

### Client conversion

When a deal is won, the system supports **Convert Opportunity → Client**. It keeps the same Account, contacts, deal, opportunity, service, value, sales history, communications, intelligence and evidence. It may create the client status, a project, project tasks, an account owner and an account manager.

### Project management (lightweight)

Projects, milestones, tasks, deadlines, owners, status, risks, notes and documents. VROS does not try to replace Jira, ClickUp or dedicated project tools.

### Client health

Each client is **Green, Yellow or Red**, based on project status, overdue work, communication, unresolved issues, milestones, satisfaction, engagement and expansion potential.

### Retention engine

Detects prolonged inactivity, unresolved issues, missed milestones, delayed projects, negative feedback, communication gaps and declining engagement. It then raises "Client Risk Detected" and assigns a follow-up task.

### Expansion engine

Finds cross-sell, upsell, additional product development, SEO, marketing, CRM, automation, mobile app, client portal, internal tools and integration opportunities. Every recommendation must be evidence-based.

### Referral management

Track referral source, referred company, relationship, referral status, conversion and revenue.

### Documents

Proposals, requirements, briefs, contracts, SOWs, meeting notes, PDFs, screenshots and project documents, each linked to the relevant records.

## 15. Discovery, monitoring, feedback and learning

### Discovery

Supported sources: direct website/URL research, public web research, company and domain discovery, a search-provider abstraction, public datasets, user CSV import, company website analysis, public announcements and public job information. No paid provider is mandatory.

### Natural-language search

Translate plain requests into structured filters and ranking criteria. Examples:

- "Find UK SaaS startups that raised funding within the last 12 months and are hiring developers."
- "Find businesses similar to Wesbridge." / "Find businesses similar to our best clients."
- "Find London professional-service firms that could benefit from CRM and client portals."
- "Find companies where a product rebuild looks likely."
- "Find 20 companies Verkies should contact this week."
- "Find companies with strong SEO opportunity but weak conversion."

### Top leads mode

"Find my next 20 leads" returns the best available prospects, not the newest. Ranking considers ICP, negative ICP, historical wins and losses, buying signals, opportunity, geography, service fit, similarity, data confidence, timing and commercial potential.

### Monitoring

Users can monitor accounts for funding, hiring, leadership changes, website changes, product launches, new services, expansion, technical changes and major announcements. A new signal may raise "Opportunity Detected" or "Account Requires Review", or create a task.

### Salesperson feedback

Good Lead · Bad Lead · Contacted · Meeting Booked · Proposal Sent · Won · Lost · Wrong Buyer · Wrong Service · Not Now · Not ICP · Duplicate · Competitor · Opportunity Confirmed · Opportunity Incorrect

All feedback is stored and used by the learning engine.

### Learning engine

It connects lead intelligence, CRM activity and sales outcomes to find patterns linked to success. Example: UK SaaS + seed funding + engineering hiring + product expansion → meeting → proposal → won.

Learning influences scoring, ranking, ICP weighting, signal importance, service matching, similarity and recommended prospects. Human override is always available.

## 16. Data quality, search, import and export

Never create duplicates silently. Every fact carries a source URL, a collection timestamp, evidence and a confidence score.

### Deduplication

Detect duplicates using combinations of domain, normalized company name, email domain, phone, legal entity and known identifiers. Show possible duplicates for review.

### Import and export

CSV import with duplicate preview, validation, field mapping and import history. CSV and JSON export.

### Global search

Covers companies, contacts, leads, opportunities, deals, projects, tasks, notes, activities and evidence, with fuzzy matching.

## 17. Security, compliance, access and crawling

### Security controls

Authentication, role-based access control, authorization, secure password handling, session management, input validation, SQL-injection protection, XSS protection, CSRF protection where applicable, SSRF protection, rate limiting, secure secrets, audit logs, encrypted sensitive credentials, safe file handling and secure API endpoints.

### Roles (RBAC)

Admin · Founder / Management · Sales Manager · Salesperson · Researcher · Project Manager · Viewer. Permissions are configurable.

### Audit log

Records user, timestamp, object, action, old value, new value, source and reason where applicable. Examples: lead rejected, score changed, deal stage changed, owner reassigned, client created, project status changed.

### Compliance

Respect website terms, robots directives where applicable, access controls, privacy requirements, and data-protection and communication laws. Favour information that is public, verifiable and attributable.

**Never bypass** CAPTCHAs, authentication, paywalls, anti-bot protections or access restrictions.

### Crawler requirements

Robots awareness, rate limiting, per-domain concurrency controls, retries, timeouts, crawl budgets, user-agent identification, caching, duplicate-URL prevention, canonical handling, maximum page count, maximum response size, content-type validation and redirect limits. Long-running crawls run in background workers and expose progress and status.

## 18. Technology, providers, AI and data rules

The core system must run on free and open-source tools. Paid services may be added later behind interfaces, but none are mandatory: not Apollo, Hunter, LinkedIn Sales Navigator, or paid enrichment APIs.

### Technology stack

| Layer | Choice |
| --- | --- |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Queue / cache | Redis, Celery or equivalent |
| Web intelligence | Playwright, httpx, BeautifulSoup / lxml |
| Performance analysis | Lighthouse CLI |
| Local AI | Ollama with open-source local models |
| Storage | Local filesystem abstraction first; MinIO-compatible design where needed |
| Deployment | Docker, Docker Compose |

### Provider abstraction

External providers are never tightly coupled to business logic. Create interfaces for search, company discovery, enrichment, email, calendar, AI, data providers and storage. The application keeps working if a provider is unavailable.

### AI rules

AI is used for summarization, classification, opportunity detection, ICP reasoning, lead explanations, sales-angle generation, service matching, similarity reasoning, research synthesis and natural-language search interpretation.

AI is never the authoritative source of facts; collected evidence is. Every AI statement is classified, and the interface shows the difference where appropriate:

| Class | Meaning |
| --- | --- |
| Fact | Directly supported by evidence |
| Inference | Reasonable interpretation of evidence |
| Recommendation | Suggested action |

### Data model requirements

Use relational PostgreSQL models, not a giant JSON-only store. Use primary keys, foreign keys, indexes, constraints, migrations, timestamps and soft deletion where appropriate. The model must support future scaling.

### Performance

Run expensive operations in background workers so UI requests never block. Cache expensive research, paginate large datasets, index the database, crawl asynchronously, show job progress, support retries and handle failures gracefully.

### Reliability

Every long-running job records status, progress, start time, completion time, error state, retry state and logs. Job statuses: Queued, Running, Completed, Failed, Cancelled, Retrying.

## 18A. Free tools and data sources

Every tool below is free and needs no paid plan. Each is the most efficient free option for its job; build each one behind its provider interface (Section 18) so it can be swapped later. As of October 2026.

### Rules for using them

- **Official API or structured feed first, crawling second.** A keyless JSON feed is faster and more reliable than parsing HTML.
- **Cache everything.** Store raw responses with a fetch timestamp; re-fetch only when stale (company facts: 30 days; jobs and news: daily).
- **Respect each source's limits** with a per-source rate limiter in the worker queue.
- **Every fact keeps its source URL** so it becomes Evidence (Section 6).

### Company facts and verification

| Tool | Use in VROS | Notes |
| --- | --- | --- |
| [Companies House API](https://forum.companieshouse.gov.uk/t/companies-house-api-limits/8626) | UK legal name, company number, status (active/dissolved), incorporation date, SIC codes, registered address, officers (directors), filing history | Free key. Limit 600 requests per 5 minutes. Use the Streaming API to watch tracked companies instead of polling. Primary source for the UK, Verkies' Priority 1 market. |
| Companies House bulk data | Load the full UK company register into PostgreSQL once a month | Free download. Enables local search by SIC code, location and age with zero API calls. |
| SEC EDGAR | US filings, including Form D (private funding raises) | Free, keyless; requires a descriptive User-Agent. Form D is the best free US funding signal. |
| Wikidata (SPARQL) | Founders, HQ, industry, website for better-known companies | Free; fills gaps outside the UK and US. |

### Website, SEO, conversion and technology analysis

| Tool | Use in VROS | Notes |
| --- | --- | --- |
| httpx + selectolax or lxml | Fast first-pass fetch and parse of static pages, robots.txt, sitemap.xml, headers, SSL | Use for every site first; much cheaper than a browser. |
| Playwright (Chromium) | Render JavaScript-heavy sites, detect forms, CTAs, chat widgets, logins | Only when the static fetch finds too little. |
| Lighthouse CLI | Performance, accessibility, SEO and best-practice scores | Run on the homepage plus one key page, not every page. |
| Open-source Wappalyzer rules (the community-maintained fork) | Technology detection: CMS, frameworks, analytics, chat, payments | Load the JSON rules into your own matcher; no API calls. |
| Python `ssl`, `dnspython` | Certificate expiry, MX records, SPF/DMARC | Quick technical-health and email-setup checks. |

### Buying signals

| Tool | Signal | Notes |
| --- | --- | --- |
| Greenhouse job board API (`boards-api.greenhouse.io/v1/boards/<token>/jobs`) | Developer, CTO and product hiring | Public, keyless JSON. |
| Lever postings API (`api.lever.co/v0/postings/<site>?mode=json`) | Same | Public, keyless JSON. |
| Ashby posting API (`api.ashbyhq.com/posting-api/job-board/<name>`) | Same; common with funded startups | Public, keyless JSON. |
| Workable widget API (`apply.workable.com/api/v1/widget/accounts/<subdomain>`) | Same | Public, keyless JSON. |
| Careers-page crawl | Hiring at companies without a known job board | Detect the job-board token from links on the careers page, then use the APIs above. |
| Google News RSS + company blog/press RSS | Funding, launches, leadership changes, expansion | Free RSS; the AI classifies each item into a signal type. |
| SEC EDGAR Form D + Companies House filings (share allotments, new officers) | Funding and leadership changes | Official, dated, attributable. |
| Website snapshots (own store) | Website redesign or new service pages | Diff each monitored site's key pages weekly. |

### Discovery

| Tool | Use in VROS | Notes |
| --- | --- | --- |
| Companies House bulk data | UK prospect lists by SIC code, region and company age | Best free UK discovery source. |
| SearXNG (self-hosted) | General web search for natural-language discovery | Free metasearch with a JSON API; keep request rates low to avoid upstream blocks. |
| Common Crawl index | Find sites by technology or text pattern at scale | Free, batch-style; good for one-off list building. |
| Job board APIs (above) | "Companies hiring developers right now" | Discovery and signal in one call. |
| CSV import | Lists Verkies already has (events, directories, referrals) | Always supported. |

### Decision makers and contacts

| Tool | Use in VROS | Notes |
| --- | --- | --- |
| Companies House officers | UK directors' names and roles | Official. Names only, no contact details. |
| Team, about and leadership pages | Founder, CTO, Head of Product names and titles | Crawled and stored with source URL. LinkedIn profiles are added manually (Section 12A), and the free LinkedIn Connections export maps warm paths. |
| Email pattern + MX check | Suggested email (e.g. first@domain) marked **Unverified** | DNS check only; never SMTP probing. Shown as a suggestion, not a fact. |

### AI (local, via Ollama)

Pick models by the machine's GPU memory. Set `num_ctx` (Ollama defaults to a 4,096-token context) and use JSON-schema output for every classification task.

| Machine | Reasoning and writing | Structured JSON tasks | Embeddings (similarity, search) |
| --- | --- | --- | --- |
| 8 GB GPU / laptop | `deepseek-r1:8b` | `granite4.2:3b` | `nomic-embed-text` |
| 16 GB GPU | `gpt-oss:20b` | `granite4.2:8b` | `nomic-embed-text` |
| 24 GB GPU | `qwen3:30b` | `mistral-small3.2:24b` | `nomic-embed-text` |

Store embeddings in PostgreSQL with **pgvector**, so the Similar Client Engine needs no extra database. Model list from [this August 2026 ranking](https://www.morphllm.com/best-ollama-models); re-check before setup, since models change often.

### Platform

| Need | Free tool |
| --- | --- |
| Database + vector search | PostgreSQL + pgvector |
| Full-text and fuzzy search | PostgreSQL `tsvector` + `pg_trgm` |
| Queue and cache | Redis + Celery |
| File storage | Local disk, MinIO later |
| Email and calendar | Gmail API / Microsoft Graph (free with existing accounts), IMAP/SMTP |
| Auth | FastAPI + an open-source auth library; no paid identity provider |
| Monitoring and logs | Structured logs + Grafana/Prometheus (Phase 7) |
| Deployment | Docker Compose on one machine or a small VPS |

### Not used

LinkedIn scraping or automation (breaks its terms; LinkedIn is used manually as in Section 12A), paid enrichment (Apollo, Hunter, Clearbit, Crunchbase), SMTP mailbox probing, and any tool that bypasses CAPTCHAs or logins.

## 19. User experience

The product should feel like an enterprise revenue platform. It must not feel like a scraping dashboard, a developer admin panel, a spreadsheet or a generic CRM template. Design for clarity, speed, evidence, actionable information, minimal noise and decision-making.

### Home dashboard

Answers one question: **"What should I do today?"** It shows the highest-priority leads, today's follow-ups, overdue activities, upcoming meetings, opportunities needing attention, pipeline, new buying signals, client risks and expansion opportunities.

### Account page

The central intelligence and CRM workspace. It brings together business intelligence, sales history, client history, project history and future opportunities (see Account 360 in Section 12).

## 20. Development phases and first vertical slice

Phase 1 must work reliably end to end before the discovery engine or any later phase is built.

### Phases

1. **Phase 1 — Vertical slice:** direct URL → intelligence → qualification → scoring → CRM.
2. **Phase 2 — Discovery:** public discovery, search providers, company discovery, deduplication, enrichment, buying signals, decision-maker research.
3. **Phase 3 — Full CRM:** contacts, activities, tasks, pipelines, opportunities, deals, forecasting, communication integrations, built-in email and LinkedIn outreach (Sections 12A–12B).
4. **Phase 4 — Client lifecycle:** client conversion, projects, milestones, client health, retention, expansion, referrals.
5. **Phase 5 — Learning:** win/loss analysis, feedback, learned ICP, scoring optimization, signal effectiveness, similarity learning.
6. **Phase 6 — Monitoring:** company monitoring, website changes, funding, hiring, leadership, product announcements, expansion.
7. **Phase 7 — Enterprise hardening:** performance, security review, audit, RBAC refinement, observability, backups, disaster recovery, scalability.

### Phase 1 flow

1. User enters a company URL.
2. System crawls the website.
3. System extracts company information, technology, SEO, conversion, product, content and technical observations.
4. System identifies opportunities.
5. System evaluates ICP.
6. System evaluates negative ICP.
7. System calculates scores.
8. System collects evidence.
9. System generates the Lead Brief.
10. User approves or rejects.
11. An approved prospect becomes an Account + Lead.
12. System creates the Next Action / Task, visible in CRM Account 360.

### Definition of done for the first vertical slice

A user can:

- [ ] Enter a company URL
- [ ] Start research
- [ ] See crawl progress
- [ ] View company intelligence
- [ ] See detected opportunities
- [ ] See the ICP score
- [ ] See the negative-ICP evaluation
- [ ] See the priority score
- [ ] See the evidence
- [ ] See why Verkies should care
- [ ] See the recommended service
- [ ] See relevant Verkies project similarity
- [ ] Approve or reject the prospect
- [ ] Automatically create or update the Account
- [ ] Create the Lead
- [ ] Create the next action
- [ ] View the account in the CRM
- [ ] See the complete timeline

## 21. Engineering standards, testing and success measures

### Required engineering documents

Create these before major implementation. They become the engineering source of truth: `ARCHITECTURE.md`, `PRODUCT_SPEC.md`, `ICP_SPEC.md`, `DATA_MODEL.md`, `PROVIDER_SPEC.md`, `AI_SPEC.md`, `SCORING_SPEC.md`, `SECURITY.md`, `ROADMAP.md`.

### Engineering standards

- **Use:** modular architecture, reusable components, typed interfaces, migrations, automated tests, structured logging, error handling, background jobs, database constraints, indexes, API validation, secure defaults.
- **Avoid:** giant files, duplicated logic, hard-coded scoring, hard-coded providers, unstructured database records, magic values, and fake or mock features presented as complete.

### Testing

| Level | Covers |
| --- | --- |
| Unit | ICP scoring, negative ICP, opportunity detection, scoring, deduplication, similarity, service matching, evidence validation |
| Integration | Crawler, database, workers, AI provider, search provider, CRM relationships |
| End-to-end | Discover → Crawl → Analyze → Qualify → Score → Lead Brief → Approve → Account → Lead → Task; and Lead → Opportunity → Deal → Won → Client → Project → Expansion |

### Acceptance criteria

Scraping websites is not success on its own. The product must show:

| Area | It can… |
| --- | --- |
| Qualification | Tell good prospects from irrelevant companies, reject unsuitable ones, and explain the decision |
| Intelligence | Find meaningful commercial opportunities, provide evidence, and separate fact from inference |
| Sales | Identify likely buyers, recommend a relevant service, and create a next action |
| CRM | Manage Account → Lead → Opportunity → Deal, track contacts and activities, manage follow-ups, and track pipeline |
| Client lifecycle | Turn a won deal into a Client with Projects, a health status and expansion opportunities |
| Learning | Store feedback and won/lost outcomes, and use them to influence future ranking |

### Key product metrics

| Area | Metrics |
| --- | --- |
| Lead quality | Qualified Lead Precision, rejection rate, qualification rate, opportunity confirmation rate |
| Sales | Contact rate, response rate, meeting rate, proposal rate, win rate, average deal value, sales cycle |
| Intelligence | Evidence coverage, data confidence, signal accuracy, opportunity accuracy |
| CRM | Follow-up completion, stale opportunity rate, overdue task rate, pipeline velocity |
| Client | Retention, expansion, referral, client health |

## 22. Anti-goals and final product definition

### Anti-goals

VROS must not become:

1. **A lead quantity machine.** More leads do not mean more revenue.
2. **An Apollo clone.** Intelligence comes before contact volume.
3. **A scraping platform.** Scraping is infrastructure, not the product.
4. **A generic CRM.** The CRM is deeply connected to Verkies intelligence.
5. **A spam automation tool.** No uncontrolled mass outreach.
6. **An AI hallucination engine.** Recommendations are grounded in evidence.
7. **A Jira replacement.** Project management stays lightweight.
8. **A marketing automation monster.** Build only what contributes to Verkies revenue or the client lifecycle.

### Four integrated layers

| Layer | Purpose |
| --- | --- |
| Intelligence | Find and understand opportunities |
| CRM | Manage relationships and sales |
| Client management | Manage customers and lightweight projects |
| Learning | Learn from sales and customer outcomes |

### What VROS must answer for any relevant company

Who are they? What do they do? Why are they a fit for Verkies? What problem or opportunity do they have? What evidence proves it? Why now? Who should we speak to? What should we sell them? Which Verkies project is relevant? What should we say? What could go wrong? What happened with this account before? What is the potential value? What should the salesperson do next? What might this client need after the first project?

### Final principle

**Better decisions, not more data.** The goal is not "find more companies". It is to find the right companies, understand why they need Verkies, connect that opportunity to the right buyer and service, convert them into clients, manage the relationship, identify what they need next, and learn from every outcome.

## 23. Instructions to Claude Code

Before writing substantial code, follow these steps in order. Optimize for a reliable, evidence-backed, high-precision revenue workflow, not for feature count.

1. Inspect the existing repository completely.
2. Do not overwrite or restructure existing work blindly.
3. Identify what already exists.
4. Compare the repository against this document.
5. Produce a gap analysis.
6. Propose the target architecture.
7. Create the required engineering documents (Section 21).
8. Design the PostgreSQL data model around the Account as the central entity (Section 6).
9. Implement the first vertical slice end to end (Section 20).
10. Keep all external providers behind interfaces.
11. Use only the free tools and data sources in Section 18A, each behind its provider interface.
12. Never create fake integrations or placeholder features and present them as complete.
13. Write tests for the core qualification and CRM logic.
14. Keep the system modular, so discovery, enrichment, communication, monitoring and learning can be added later without rewriting the core.

**Recommended build order:** PRD → Data Model → Architecture → API Specification → UI/UX Specification → Scoring/ICP Engine → First Vertical Slice → Full CRM → Client Lifecycle → Learning Engine.
