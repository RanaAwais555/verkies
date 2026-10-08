"use client";

import { useState } from "react";

import { Badge, BandBadge, Card, label, Score, ScoreBar, SourceLink } from "@/components/ui";
import type { Assessment, Brief, BriefClaim, Evidence } from "@/lib/types";

const SECTION_TITLES: Record<string, string> = {
  company_overview: "Company overview",
  problem_detected: "Problem detected",
  why_verkies: "Why Verkies",
  why_now: "Why now",
  recommended_service: "Recommended service",
  best_buyer: "Best buyer",
  similar_project: "Similar Verkies work",
  sales_angle: "Sales angle",
  risks: "Risks",
  next_action: "Recommended next action",
};

const CLASS_TONE = { fact: "green", inference: "blue", recommendation: "purple" } as const;

export function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  return (
    <ul className="mt-1 space-y-1 border-l-2 border-border pl-3">
      {evidence.map((e) => (
        <li key={e.id} className="text-xs">
          <q className="text-foreground">{e.excerpt}</q>
          <div className="flex flex-wrap items-center gap-2">
            <SourceLink url={e.source_url} />
            <span className="text-muted">{label(e.evidence_type)} · confidence {Math.round(e.confidence * 100)}%</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

function ClaimView({ claim }: { claim: BriefClaim }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="space-y-1" data-testid="claim" data-class={claim.claim_class}>
      <div className="flex items-start gap-2">
        <Badge tone={CLASS_TONE[claim.claim_class]}>{label(claim.claim_class)}</Badge>
        <span className="text-sm">{claim.text}</span>
      </div>
      {claim.evidence.length > 0 && (
        <button className="ml-1 text-xs text-muted underline underline-offset-2" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Hide" : "Show"} evidence ({claim.evidence.length})
        </button>
      )}
      {open && <EvidenceList evidence={claim.evidence} />}
    </li>
  );
}

export function BriefView({ brief }: { brief: Brief }) {
  const s = brief.summary;
  const dims = ["icp_score", "opportunity_score", "intent_score", "buyer_confidence", "data_confidence"];
  return (
    <div className="space-y-4" data-testid="brief">
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold">{s.company ?? s.domain}</h2>
          <BandBadge band={s.priority_band} />
          <span className="text-sm">Priority <Score value={s.priority_score} className="font-semibold" /></span>
          {s.qualifies ? <Badge tone="green">Qualifies</Badge> : <Badge>Does not qualify</Badge>}
          <Badge title="How this brief was written">{brief.mode === "ai" ? "AI-written, evidence-checked" : "Template"}</Badge>
        </div>
        <div className="mt-3 space-y-1.5">
          {dims.map((d) => <ScoreBar key={d} name={d} value={s[d] as number | null} />)}
        </div>
        <p className="mt-3 text-xs text-muted">
          Every fact and inference links to the page it came from. Unknown means no evidence was found, not a low score.
        </p>
      </Card>
      {Object.entries(SECTION_TITLES).map(([key, title]) => {
        const section = brief.sections[key];
        if (!section) return null;
        return (
          <Card key={key} title={title} actions={section.source === "ai" ? <Badge tone="blue">AI</Badge> : undefined}>
            {section.claims.length > 0 ? (
              <ul className="space-y-2">{section.claims.map((c) => <ClaimView key={c.claim_id} claim={c} />)}</ul>
            ) : (
              <p className="text-sm text-muted" data-testid="unknown">{section.unknown ?? "Unknown"}</p>
            )}
            {section.notes.length > 0 && <p className="mt-2 text-xs text-muted">{section.notes.join(" ")}</p>}
          </Card>
        );
      })}
    </div>
  );
}

export function AssessmentView({ assessment }: { assessment: Assessment }) {
  const { qualification: q, score } = assessment;
  return (
    <div className="space-y-4">
      <Card title="Detected opportunities">
        {assessment.opportunities.length === 0 ? (
          <p className="text-sm text-muted">No evidenced opportunity.</p>
        ) : (
          <ul className="space-y-3">
            {assessment.opportunities.map((o) => (
              <li key={o.id} className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{o.title}</span>
                  <Badge>{label(o.category)}</Badge>
                  <span className="text-xs text-muted">confidence {Math.round(o.confidence * 100)}%</span>
                </div>
                <p className="text-sm">{o.problem}</p>
                <EvidenceList evidence={o.evidence} />
              </li>
            ))}
          </ul>
        )}
      </Card>
      {q && (
        <Card title="Qualification (ICP)">
          <p className="text-sm">ICP fit <Score value={q.icp_fit} /> {q.hard_reject && <Badge tone="red">Rejected: {label(q.rejection_reason ?? "")}</Badge>}</p>
          <p className="mt-2 whitespace-pre-line text-sm text-muted">{q.explanation}</p>
        </Card>
      )}
      {score && (
        <Card title="Scores">
          <div className="space-y-1.5">
            {Object.entries(score.scores).map(([k, v]) => <ScoreBar key={k} name={k} value={v} />)}
          </div>
          {score.not_qualified_because.length > 0 && (
            <p className="mt-3 text-sm text-muted">Not qualified because: {score.not_qualified_because.join("; ")}</p>
          )}
        </Card>
      )}
    </div>
  );
}
