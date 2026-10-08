# VROS Scoring Specification

Implements §10. Every weight, threshold and gate below is a **default** stored in `scoring_configs` (versioned, admin-editable). None is hard-coded. Changing a config creates a new version; old score snapshots keep the version they used.

## 1. Principles

1. Ten dimensions, each 0–100, each independently explainable.
2. **Unknown is not zero.** A dimension with no usable inputs is `null`, excluded from the combination, and counted against coverage and data confidence.
3. Every score stores a `breakdown`: inputs used, input source (evidence IDs), weight, contribution, and the inputs that were Unknown.
4. Scores are deterministic functions of stored evidence and config. AI may explain a score but never sets one.
5. Scoring is append-only: each run writes a `score_snapshot`; the account's cached scores copy the latest.

## 2. Dimensions

| # | Dimension | Meaning | Phase 1 inputs (all evidence-backed) |
| --- | --- | --- | --- |
| 1 | ICP Fit | Match to the Master ICP | ICP engine output (ICP_SPEC.md) |
| 2 | Opportunity | Strength of the detected commercial opportunity | Opportunity candidates: count, confidence, evidence per candidate, category value weight |
| 3 | Intent | Evidence the company is actively changing or building | Careers page with engineering/product roles, product launch or "coming soon" mentions, recent blog/news dates, rebuild or migration mentions. Funding and job-board signals added in Phase 2 |
| 4 | Buyer Confidence | A relevant decision maker is reasonably identifiable | Named people on team/about pages with matching roles, published contact route, warm path (Phase 3) |
| 5 | Data Confidence | How much of the account data is verified | Share of key account fields with evidence, mean evidence confidence, freshness |
| 6 | Service Fit | A plausible Verkies service matches | Best service match confidence from the catalogue |
| 7 | Timing | Urgency | Recency of dated signals; Unknown when nothing is dated |
| 8 | Commercial Potential | Likely deal size and budget indicators | Pricing page tier, enterprise indicators, team size bands, product complexity, industry tier |
| 9 | Client Similarity | Likeness to Verkies' previous work | Best reference-project similarity; Unknown when no reference profile is complete |
| 10 | Evidence Strength | Quantity, diversity and quality of evidence | Distinct evidence items, distinct source pages, evidence types, mean confidence |

Each dimension's function is a documented pure function in `app/scoring/dimensions/<name>.py` with unit tests covering the Unknown case.

## 3. Default weights

| Dimension | Weight |
| --- | --- |
| ICP Fit | 0.20 |
| Opportunity | 0.20 |
| Intent | 0.12 |
| Service Fit | 0.10 |
| Buyer Confidence | 0.08 |
| Data Confidence | 0.08 |
| Commercial Potential | 0.08 |
| Timing | 0.06 |
| Client Similarity | 0.04 |
| Evidence Strength | 0.04 |
| **Total** | **1.00** |

Config validation rejects weights that do not sum to 1.00.

## 4. Priority score

```
known   = dimensions with a non-null score
coverage = sum(weight of known) / sum(weight of all)
raw     = sum(weight_i * score_i for known) / sum(weight of known)
priority = apply_gates(raw, coverage)
```

Gates, evaluated in order, each recording itself in the breakdown:

| Gate | Default condition | Effect |
| --- | --- | --- |
| Hard reject | ICP engine returned `hard_reject` | priority capped at 39 (Reject band) |
| Coverage | `coverage < 0.50` | capped at 59 (Monitor) |
| Evidence | Evidence Strength `< 30`, or the opportunity has no supporting evidence | capped at 59 |
| Service | No service match | capped at 59 |
| Data confidence | Data Confidence `< 40` | capped at 74 (Qualified) |

## 5. Qualification (§10 rules)

A prospect `qualifies` only if all hold (defaults, configurable):

- ICP Fit ≥ 50 and not hard-rejected
- at least one opportunity candidate with supporting evidence
- Evidence Strength ≥ 30 and Data Confidence ≥ 40
- at least one strong buying signal, **or** at least two independent verified problem signals
- a service match exists

`Hot` and `High priority` bands require `qualifies = true`. If the score would fall in those bands but the prospect does not qualify, the band is `Qualified` and the reason is shown.

## 6. Bands (default)

| Priority | Band |
| --- | --- |
| 90–100 | Hot, contact now |
| 75–89 | High priority |
| 60–74 | Qualified, research further |
| 40–59 | Monitor |
| < 40 | Reject / suppress |

## 7. Learning hook (Phase 5)

`learned_weights` can propose a new `scoring_configs` version from win/loss data. A proposal is never activated automatically; a human activates it, and can always override (§15).

## 8. Tests

- Each dimension: known inputs, partial inputs, no inputs (null).
- Priority: weights sum, renormalisation over known dimensions, each gate alone and combined, band boundaries (39/40, 59/60, 74/75, 89/90).
- Config validation: weights must sum to 1; thresholds must be ordered.
- Golden files: five fixture sites (strong SaaS, weak local business, parked domain, agency, personal portfolio) with expected score ranges and bands.
