# VROS AI Specification

Implements §3 (no hallucinations, evidence first) and §18 (AI rules). **AI is never the authoritative source of facts. Collected evidence is.**

## 1. What AI does and does not do

| Does | Does not |
| --- | --- |
| Summarise and classify evidence (industry, business model) | Set any score |
| Write the lead-brief prose (Why Verkies, Why Now, Sales angle, Risks) | Decide ICP, hard rejection or qualification |
| Explain detected opportunities in business terms | Invent companies, people, titles, funding, headcount, revenue, technologies, clients, quotes or case studies |
| Draft outreach (Phase 3) | Send anything |
| Interpret natural-language search into filters (Phase 2) | Fill gaps with guesses; gaps are **Unknown** |

Deterministic rules own the decisions. AI owns the wording and the soft classifications, and everything it says is checked.

## 2. Claim classes

Every statement shown in the product has a class:

| Class | Meaning | Requirement |
| --- | --- | --- |
| Fact | Directly supported by evidence | At least one real evidence ID whose text supports it |
| Inference | Reasonable interpretation of evidence | At least one evidence ID; wording marked as inferred |
| Recommendation | Suggested action | Links to the facts/inferences it rests on |

The UI renders the three differently. Unverified information is shown as **Unknown**.

## 3. Grounding protocol

1. **Input is closed.** The prompt contains only: the evidence items for this run (each with an ID, source URL and excerpt), the structured outputs of the ICP, scoring and detection engines, and the service and reference-project catalogue. No other facts are supplied and the model is told it has none.
2. **Output is structured.** The model returns JSON validated against a schema. Every claim has `class`, `text`, `evidence_ids[]`.
3. **Post-validation.** For each claim:
   - every `evidence_id` must exist in this run's evidence set;
   - a Fact or Inference with no valid evidence ID is dropped;
   - numbers, names, dates and URLs in the text must appear in the cited evidence excerpt (string/regex check); a claim failing this is dropped.
4. **Dropped claims are logged** with the reason, and the brief section shows Unknown if nothing survives.
5. **Provenance stored.** `lead_briefs.generated_by` holds provider, model, prompt version and parameters, so a brief can be reproduced and audited.
6. **Banned phrases.** Generic filler such as "help your business grow" is rejected by a validator; a section must name a specific observed problem or it is not shown.

## 4. Why Verkies and Why Now

- **Why Verkies** must reference the detected opportunity, the matched service, the evidence, and, only if a complete reference-project profile exists, the similar project. If no reference profile is complete the sentence is omitted, not invented.
- **Why Now** must cite a dated or time-bound evidence item (hiring, launch, rebuild, expansion, funding). With none, it reads "No time-bound signal found" rather than manufacturing urgency.

## 5. Models (Ollama, local)

Chosen by GPU memory (§18A). `num_ctx` is set explicitly (Ollama defaults to 4,096). Every classification task uses JSON-schema constrained output.

| Machine | Reasoning/writing | Structured JSON | Embeddings |
| --- | --- | --- | --- |
| 8 GB | `deepseek-r1:8b` | `granite4.2:3b` | `nomic-embed-text` |
| 16 GB | `gpt-oss:20b` | `granite4.2:8b` | `nomic-embed-text` |
| 24 GB | `qwen3:30b` | `mistral-small3.2:24b` | `nomic-embed-text` |

Model names change quickly; they are settings, and the list is re-checked at setup. Embeddings (768-d) are stored with pgvector for similarity and search.

## 6. Degradation

`AIProvider` has a `NullProvider`. With no model reachable:

- ICP, negative ICP, opportunity detection, scoring, service matching and approval all work (they are deterministic).
- Industry classification falls back to keyword/structured-data rules, else Unknown.
- The brief is rendered from a deterministic template that states each finding and its evidence, with no flourish. It is labelled "template".
- Similarity falls back to structured-field overlap with no embedding.
The UI shows which mode produced each brief.

## 7. Prompt management

Prompts live in `app/briefs/prompts/` as versioned files with a version string stored on each output. A prompt change requires re-running the evaluation set (§8).

## 8. Evaluation

- A fixture set of stored crawls (five from SCORING_SPEC.md §8, growing over time) with expected: industry, opportunity categories, services, and a list of "must not appear" facts.
- Checks: no claim without valid evidence; zero invented entities (names, numbers and URLs not in evidence); expected categories found; Unknown used where evidence is absent.
- Runs in CI against `NullProvider` plus a recorded-response fake. A live-model run is a manual release check.
- Production metric: share of briefs where a salesperson marks a claim wrong (feeds the learning loop, Phase 5).

## 9. Privacy

Local models mean company text stays on Verkies infrastructure. If a hosted model is added later, it is an explicit provider setting, off by default, and personal data is minimised before sending.
