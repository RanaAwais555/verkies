import { AlertTriangle, BarChart3, CircleHelp, Radio, Target, type LucideIcon } from "lucide-react";
import Link from "next/link";

import { BandBadge, Badge, ScoreChip, SourceLink } from "@/components/ui";
import { formatDate, initials, label } from "@/lib/format";
import type { RankedLead, RankReason } from "@/lib/types";

const KIND: Record<RankReason["kind"], { icon: LucideIcon; tint: string; title: string }> = {
  score: { icon: BarChart3, tint: "text-accent-text", title: "Score" },
  signal: { icon: Radio, tint: "text-ok", title: "Signal" },
  opportunity: { icon: Target, tint: "text-violet", title: "Opportunity" },
  gate: { icon: AlertTriangle, tint: "text-warn", title: "Cap" },
  unknown: { icon: CircleHelp, tint: "text-fg-3", title: "Unknown" },
};

/** One ranked lead: who, how it scores, and why it sits at this rank, each reason from stored data. */
export function LeadCard({ lead }: { lead: RankedLead }) {
  const a = lead.account;
  return (
    <article className="lift grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-3 rounded-xl border border-border/80 bg-surface p-5" data-testid="lead">
      <div className="flex flex-col items-center gap-2">
        <span className="tabular text-[13px] font-semibold text-fg-3" aria-label={`Rank ${lead.rank}`}>
          #{lead.rank}
        </span>
        <span aria-hidden className="grid h-12 w-12 place-items-center rounded-xl bg-accent-soft text-sm font-semibold text-accent-text">
          {initials(a.name)}
        </span>
      </div>
      <div className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <Link href={`/accounts/${a.id}`} className="text-[16px] font-semibold text-fg hover:text-accent-text">
              {a.name}
            </Link>
            <p className="text-[13px] text-fg-3">
              {[a.primary_domain, a.industry, a.hq_country].filter(Boolean).join(" · ") || "No details yet"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <ScoreChip value={a.priority_score} />
            <BandBadge band={a.priority_band} />
            <Badge>{label(a.account_type)}</Badge>
          </div>
        </div>
        <ul className="space-y-1.5" aria-label="Why it ranks here">
          {lead.reasons.map((r, i) => {
            const { icon: Icon, tint, title } = KIND[r.kind] ?? KIND.unknown;
            return (
              <li key={i} className="flex items-start gap-2 text-[13px] leading-relaxed text-fg-2">
                <Icon aria-label={title} className={`mt-[3px] h-3.5 w-3.5 shrink-0 ${tint}`} />
                <span className="min-w-0">
                  {r.text}
                  {r.source_url && (
                    <span className="ml-2 text-xs">
                      <SourceLink url={r.source_url} />
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
        <p className="text-xs text-fg-3">
          Owner: {a.owner?.name ?? "unassigned"} · next activity {a.next_activity_at ? formatDate(a.next_activity_at) : "none set"}
          {lead.scored_at && ` · scored ${formatDate(lead.scored_at)}`}
        </p>
      </div>
    </article>
  );
}
