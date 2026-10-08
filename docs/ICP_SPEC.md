# VROS ICP Specification

Implements §5. The ICP is data, held in `icp_configs` (versioned, one active). The engine reads it; nothing below is hard-coded. **Industry or geography alone never qualifies a lead.**

## 1. Master ICP

A commercially active startup, scale-up, growth-oriented or established business with a demonstrable need for software or product development (MVP, SaaS, web and mobile apps, marketplaces, internal systems, CRM, workflow automation, digital transformation), website development or rebuild, or SEO, conversion optimisation and growth marketing. It must also show evidence of budget potential, urgency, growth, operational pain, product development, hiring, funding, expansion, technical problems or digital growth opportunities, and a relevant decision maker must be reasonably identifiable.

## 2. ICP Fit calculation

ICP Fit (0–100) combines four components. Each component is null if it cannot be evidenced; null components are excluded and the remaining weights are renormalised.

| Component | Default weight | How it is computed |
| --- | --- | --- |
| Need evidence | 0.35 | Strength of evidence for a need in the Master ICP: highest-confidence opportunity candidate, plus count of independent need signals |
| Industry | 0.30 | Tier S = 100, A = 75, B = 50, other = 20, unknown = null |
| Business activity and stage | 0.20 | Active site, fresh content, product or service pages, team page, signs of growth (hiring, launches). Unknown size stays unknown |
| Geography | 0.15 | Priority 1 = 100, 2 = 85, 3 = 70, 4 = 65, 5 = 55, 6 = 50, other = 20, unknown = null; focus cities add +5 (cap 100) |

Tier B industries need stronger evidence: if Evidence Strength is below 50, the industry component is multiplied by 0.7 and the explanation says so.

Geography is inferred from, in order: structured data (`PostalAddress`), contact/footer address, TLD and `hreflang`, registry data (Phase 2). Each inference stores its evidence. Conflicting signals reduce confidence rather than choosing silently.

## 3. Industry tiers (default)

| Tier | Industries |
| --- | --- |
| S | SaaS, AI startups, AI SaaS, FinTech, HealthTech, PropTech, EdTech, MarTech, marketplaces, software companies, funded startups, product startups |
| A | Immigration, legal, recruitment, accounting, consulting, healthcare, logistics, travel technology, real estate, professional services, e-commerce platforms, education technology |
| B | Construction, automotive, hospitality, restaurants, retail, fitness, beauty, local services |

Industry is classified from page content (rules over keywords and structured data first, AI classification second, always with the evidence that supports it). If the classifier cannot decide, the industry is Unknown.

Implemented (`backend/app/intelligence/extractors/industry.py`): keyword rules over the homepage, about, services, product and pricing pages need at least three hits and a 1.5x lead over the runner-up; a matching JSON-LD type (e.g. `LegalService`) also counts. A site can carry more than one industry observation (e.g. immigration from its wording, legal from its schema type); the ICP uses the highest-scoring tier among them.

## 4. Geography (default)

| Priority | Region | Focus cities |
| --- | --- | --- |
| 1 | United Kingdom | London, Manchester, Birmingham, Cambridge, Oxford, Bristol, Edinburgh |
| 2 | United States | New York, San Francisco Bay Area, Austin, Boston, Seattle, Los Angeles, Chicago, Miami |
| 3 | Canada | |
| 4 | Australia | |
| 5 | Western Europe | Netherlands, Germany, France, Ireland, Switzerland, Sweden, Denmark |
| 6 | UAE | Dubai, Abu Dhabi |

## 5. Negative ICP

Each rule has an ID, a detector, a severity (**hard** or **soft**), a rejection reason (§3) and the evidence it fired on. A hard hit sets `hard_reject` and the prospect goes to Rejected. Soft hits reduce ICP Fit by a configured penalty and are shown.

| Rule | Severity | Reason | Phase 1 detector |
| --- | --- | --- | --- |
| Parked or for-sale domain | hard | inactive_company | Known parking page patterns, near-empty page, registrar/parking markers |
| Site unreachable or erroring on all pages | hard | inactive_company | Non-2xx on homepage after retries, DNS failure |
| Closed or ceased trading | hard | inactive_company | "ceased trading", "permanently closed", "we have closed" in page text, or a Companies House status of dissolved, liquidation, administration, receivership, insolvency proceedings, converted/closed or removed (slice 2.3) |
| Personal, hobby or freelancer site | hard with two or more phrases; review with one | hobby_or_personal, or student_or_freelancer when the wording is about freelancing | "hire me", "my portfolio", "freelance web developer", "download my CV" |
| Student, freelancer or job seeker | hard | student_or_freelancer | "hire me", "freelance", "open to work", CV/portfolio structure, single-person offering |
| Influencer or personal brand | soft→hard if no business product | hobby_or_personal | Link-in-bio structure, sponsorship and merch pages, no product |
| Agency or competitor | **routed**, see §6: hard with two or more phrases or the word "agency"; review with one | competitor | "digital agency", "we build websites for", "white-label services", "our clients include" |
| Duplicate | review | duplicate | Domain already belongs to an account. Not a rejection: approval updates that account (`DATA_MODEL.md` §3) |
| Suppressed account | hard | suppressed_account | Matches `suppressions` |
| No identifiable commercial opportunity | soft | no_commercial_opportunity | No opportunity candidate above minimum confidence |
| No plausible service fit | soft | no_relevant_service | No service match |
| Insufficient evidence | soft | insufficient_evidence | Evidence Strength below threshold |
| No plausible buyer | soft | no_reachable_buyer | No named person or contact route found |
| Unsuitable size | soft | unsuitable_company_size | Only when size is evidenced |
| Existing solution sufficient | soft | existing_solution_sufficient | Strong conversion path and modern product evidence with no problem signals |
| Irrelevant industry | soft | irrelevant_industry | Industry known and outside all tiers |

A **review** hit neither rejects nor penalises; it is shown to the person approving.

Detectors are conservative on **hard** rules: they require explicit evidence, and an ambiguous case becomes a soft hit with a "needs review" flag, not a silent rejection.

## 6. Agencies

Agencies never enter the standard sales queue automatically. When the agency detector fires, the account is created only on approval, with `agency_class` set by the reviewer to one of competitor, potential partner, referral partner, white-label partner or subcontracting opportunity, and it is routed to the Partnership pipeline (Phase 3). Until Phase 3 the class is stored and the account is excluded from the lead queue.

## 7. Output

```
{
  icp_fit: 0-100 | null,
  components: [{name, score|null, weight, evidence_ids, note}],
  negative_icp_hits: [{rule_id, severity, reason, evidence_ids}],
  hard_reject: bool,
  rejection_reason: enum | null,
  explanation: string      # generated from the components, not from AI
}
```

## 8. Tests

Unit tests per rule (positive, negative, ambiguous) and per component (known and Unknown). Fixture sites as listed in SCORING_SPEC.md §8. A rule change that flips a golden-file outcome fails CI until the expected outcome is reviewed.

## 9. Implementation

`backend/app/qualification/icp.py` (engine) and `config.py` (defaults, validation). Version 1 is seeded by migration `0006`; admins create new versions with `PUT /api/v1/config/icp` (validated, audited, the old version kept). Each qualification result stores the config version it used. Tests: `backend/tests/unit/test_assessment.py` (golden sites: service firm, SaaS, holding page, parked, closed, freelancer, agency).
