import { SourceLink } from "@/components/ui";
import { label, percent } from "@/lib/format";
import type { Evidence } from "@/lib/types";

/** The quoted excerpts behind a claim, each with its source page, type and confidence. */
export function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  return (
    <ul className="mt-2 space-y-2.5 border-l-2 border-accent/30 pl-3.5">
      {evidence.map((e) => (
        <li key={e.id} className="space-y-1 text-xs">
          <q className="leading-relaxed text-fg">{e.excerpt}</q>
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <SourceLink url={e.source_url} />
            <span className="text-fg-3">
              {label(e.evidence_type)} · confidence {percent(e.confidence)}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
