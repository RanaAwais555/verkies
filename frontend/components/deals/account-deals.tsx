"use client";

import { Columns3, FolderKanban, Plus, UserCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ConvertForm } from "@/components/clients/convert";

import { Badge, Button, Empty, ErrorNote, Panel, ShowAll } from "@/components/ui";
import { api } from "@/lib/client";
import { formatDate, money } from "@/lib/format";
import { useAction, useCanChange } from "@/lib/hooks";
import type { Deal } from "@/lib/types";

const OUTCOME_TONE = { open: "accent", won: "green", lost: "red", nurture: "amber", inactive: "neutral" } as const;

/** Open a deal from an opportunity; it starts at the stage the opportunity has reached. */
export function OpenDealButton({ opportunityId, onOpened }: { opportunityId: string; onOpened: () => void }) {
  const { busy, error, run } = useAction();
  return (
    <span className="inline-flex flex-col gap-1">
      <Button
        busy={busy}
        className="h-7 px-2.5 text-xs"
        icon={<Plus className="h-3.5 w-3.5" />}
        onClick={async () => {
          if (await run(() => api("/deals", { method: "POST", body: { opportunity_id: opportunityId } }).then(() => true))) onOpened();
        }}
      >
        Open a deal
      </Button>
      <ErrorNote error={error} />
    </span>
  );
}

/** The account's deals, open and closed, each with its stage, value and close date. */
export function AccountDeals({ deals, onChange }: { deals: Deal[]; onChange: () => void }) {
  const writable = useCanChange();
  const [converting, setConverting] = useState<string | null>(null);
  return (
    <Panel
      title="Deals"
      description="Opened from this account's opportunities and worked on the pipeline board."
      footer={deals.length > 0 && <ShowAll href={`/pipeline?tab=${deals[0].pipeline_key}`}>Open the pipeline</ShowAll>}
      testId="account-deals"
    >
      {deals.length === 0 ? (
        <Empty icon={<Columns3 className="h-4 w-4" />}>No deals yet. Open one from an opportunity above.</Empty>
      ) : (
        <ul className="divide-y divide-grid">
          {deals.map((d) => (
            <li key={d.id} className="relative flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5 text-[13px] first:pt-0 last:pb-0">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-fg">{d.name}</span>
                <span className="text-xs text-fg-3">
                  {d.owner?.name ?? "No owner"}
                  {d.expected_close && ` · closes ${formatDate(d.expected_close)}`}
                  {d.lost_reason && ` · lost: ${d.lost_reason.replaceAll("_", " ")}`}
                </span>
              </span>
              <span className={d.value === null ? "tabular text-fg-3" : "tabular font-semibold text-fg"}>{money(d.value, d.currency)}</span>
              <Badge tone={OUTCOME_TONE[d.outcome]}>{d.stage_name}</Badge>
              <Link href={`/pipeline?tab=${d.pipeline_key}`} className="sr-only">
                {d.name} on the pipeline board
              </Link>
              {d.outcome === "won" && (
                <span className="basis-full">
                  {d.project_id ? (
                    <Link href={`/projects/${d.project_id}`} className="inline-flex items-center gap-1.5 text-xs font-medium text-accent-text hover:underline">
                      <FolderKanban aria-hidden className="h-3.5 w-3.5" />
                      Open the project
                    </Link>
                  ) : converting === d.id ? (
                    <ConvertForm
                      deal={d}
                      onCancel={() => setConverting(null)}
                      onDone={() => {
                        setConverting(null);
                        onChange();
                      }}
                    />
                  ) : (
                    writable && (
                      <Button className="h-7 px-2.5 text-xs" icon={<UserCheck className="h-3.5 w-3.5" />} onClick={() => setConverting(d.id)}>
                        Convert to client
                      </Button>
                    )
                  )}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
