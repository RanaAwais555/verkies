"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { EvidenceList } from "@/components/research/evidence";
import { Badge, BandBadge, ClaimTag, Note, Panel, Score, ScoreBar } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import type { Brief, BriefClaim } from "@/lib/types";

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

const SUMMARY_DIMENSIONS = ["icp_score", "opportunity_score", "intent_score", "buyer_confidence", "data_confidence"];

function Claim({ claim }: { claim: BriefClaim }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="space-y-1.5" data-testid="claim" data-class={claim.claim_class}>
      <div className="flex items-start gap-2.5">
        <ClaimTag kind={claim.claim_class} />
        <span className="text-[13.5px] leading-relaxed text-fg">{claim.text}</span>
      </div>
      {claim.evidence.length > 0 && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="ml-1 inline-flex items-center gap-1 text-xs font-medium text-accent-text hover:underline"
        >
          <ChevronRight aria-hidden className={cx("h-3.5 w-3.5 transition-transform duration-200 ease-spring", open && "rotate-90")} />
          {open ? "Hide" : "Show"} evidence ({claim.evidence.length})
        </button>
      )}
      {open && <div className="animate-rise"><EvidenceList evidence={claim.evidence} /></div>}
    </li>
  );
}

/** The evidence-linked lead brief: summary scores, then one section per question it answers. */
export function BriefView({ brief }: { brief: Brief }) {
  const s = brief.summary;
  return (
    <div className="space-y-4" data-testid="brief">
      <Panel primary>
        <div className="flex flex-wrap items-center gap-2.5">
          <h2 className="text-lg font-semibold tracking-[-0.015em] text-fg">{s.company ?? s.domain}</h2>
          <BandBadge band={s.priority_band} />
          <span className="text-[13px] text-fg-2">
            Priority <Score value={s.priority_score} className="font-semibold text-fg" />
          </span>
          {s.qualifies ? <Badge tone="green">Qualifies</Badge> : <Badge>Does not qualify</Badge>}
          <Badge title="How this brief was written" tone={brief.mode === "ai" ? "accent" : "neutral"}>
            {brief.mode === "ai" ? "AI-written, evidence-checked" : "Template"}
          </Badge>
        </div>
        <div className="mt-4 space-y-2">
          {SUMMARY_DIMENSIONS.map((d) => (
            <ScoreBar key={d} name={d} value={s[d] as number | null} />
          ))}
        </div>
        <Note className="mt-4">Every fact and inference links to the page it came from. Unknown means no evidence was found, not a low score.</Note>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-2">
        {Object.entries(SECTION_TITLES).map(([key, title]) => {
          const section = brief.sections[key];
          if (!section) return null;
          return (
            <Panel key={key} title={title} actions={section.source === "ai" ? <Badge tone="accent">AI</Badge> : undefined}>
              {section.claims.length > 0 ? (
                <ul className="space-y-3.5">
                  {section.claims.map((c) => (
                    <Claim key={c.claim_id} claim={c} />
                  ))}
                </ul>
              ) : (
                <p className="text-[13px] text-fg-3" data-testid="unknown">
                  {section.unknown ?? "Unknown"}
                </p>
              )}
              {section.notes.length > 0 && <Note className="mt-3">{section.notes.join(" ")}</Note>}
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
