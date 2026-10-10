"use client";

import { EvidenceList } from "@/components/research/evidence";
import { ErrorNote, Panel, Skeleton } from "@/components/ui";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Intelligence } from "@/lib/types";

function show(value: unknown): string {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : JSON.stringify(value);
}

/** Every raw observation the crawl made, grouped by area, each with its evidence. */
export function IntelligenceView({ runId }: { runId: string }) {
  const { data, error } = useApi<Intelligence>(`/research-runs/${runId}/intelligence`);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={6} />;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {Object.entries(data.areas).map(([area, items]) => (
        <Panel key={area} title={label(area)} collapsible>
          <ul className="divide-y divide-grid">
            {items.map((o) => (
              <li key={o.id} className="py-2.5 text-[13px] first:pt-0 last:pb-0">
                <span className="font-mono text-xs text-fg-3">{o.key}</span> <span className="text-fg">{show(o.value)}</span>
                <EvidenceList evidence={[o.evidence]} />
              </li>
            ))}
          </ul>
        </Panel>
      ))}
    </div>
  );
}
