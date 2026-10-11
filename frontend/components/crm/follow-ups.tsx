"use client";

import { AlertTriangle, Clock, Columns3, Hourglass, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { Empty, ErrorNote, Panel, Skeleton, TextLink } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { useApi } from "@/lib/hooks";
import type { FollowUpFlag, FollowUpKind, FollowUps } from "@/lib/types";

// The follow-up engine's four flags (§12), most urgent first. Overdue work and missing next actions
// are problems (red); records going quiet are warnings (amber).
export const FLAG_GROUPS: { kind: FollowUpKind; title: string; icon: LucideIcon; tone: "bad" | "warn"; testId: string }[] = [
  { kind: "overdue_follow_up", title: "Overdue follow-ups", icon: Clock, tone: "bad", testId: "overdue" },
  { kind: "no_next_action", title: "No next action", icon: AlertTriangle, tone: "bad", testId: "attention" },
  { kind: "inactive_deal", title: "Inactive deals", icon: Columns3, tone: "warn", testId: "inactive-deals" },
  { kind: "stale_opportunity", title: "Stale opportunities", icon: Hourglass, tone: "warn", testId: "stale-opportunities" },
];

function FlagGroup({
  title,
  icon: Icon,
  tone,
  testId,
  flags,
  perGroup,
}: (typeof FLAG_GROUPS)[number] & { flags: FollowUpFlag[]; perGroup: number }) {
  const [all, setAll] = useState(false);
  const shown = all ? flags : flags.slice(0, perGroup);
  return (
    <section aria-label={title} className="space-y-1.5">
      <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.08em] text-fg-3">
        <Icon aria-hidden className={cx("h-3.5 w-3.5", tone === "bad" ? "text-bad" : "text-warn")} />
        {title}
        <span className="tabular font-medium normal-case tracking-normal text-fg">{flags.length}</span>
      </h3>
      <ul className="divide-y divide-grid" data-testid={testId}>
        {shown.map((f) => (
          <li key={f.ref_id} className="py-2 text-[13px]">
            <TextLink href={`/accounts/${f.account_id}`}>{f.account_name}</TextLink>
            <span className="text-fg-3"> · {f.title}</span>
            <p className={cx("mt-0.5 text-xs", tone === "bad" ? "text-bad" : "text-warn")}>
              {f.detail}
              <span className="text-fg-3"> · {f.owner?.name ?? "no owner"}</span>
            </p>
          </li>
        ))}
      </ul>
      {flags.length > perGroup && (
        <button type="button" onClick={() => setAll(!all)} className="text-xs font-medium text-accent-text hover:underline">
          {all ? "Show fewer" : `Show all ${flags.length}`}
        </button>
      )}
    </section>
  );
}

/**
 * What needs a nudge: overdue follow-ups, missing next actions, and deals and opportunities going
 * quiet. `kinds` limits it to some flags; `mine` and `onMine` let the parent own the toggle.
 */
export function FollowUpsPanel({
  kinds,
  mine: mineProp,
  onMine,
  perGroup = 4,
}: {
  kinds?: FollowUpKind[];
  mine?: boolean;
  onMine?: (mine: boolean) => void;
  perGroup?: number;
}) {
  const [ownMine, setOwnMine] = useState(false);
  const mine = mineProp ?? ownMine;
  const setMine = onMine ?? setOwnMine;
  const { data, error } = useApi<FollowUps>(`/follow-ups${mine ? "?mine=true" : ""}`);
  const groups = FLAG_GROUPS.filter((g) => !kinds || kinds.includes(g.kind))
    .map((g) => ({ ...g, flags: data?.flags.filter((f) => f.kind === g.kind) ?? [] }))
    .filter((g) => g.flags.length > 0);
  return (
    <div id="follow-ups" className="scroll-mt-20">
      <Panel
        title="Follow-ups"
        description={
          data
            ? `From tasks, activity and stage moves. Quiet means ${data.stale_opportunity_days} days for an opportunity, ${data.inactive_deal_days} for a deal.`
            : "From tasks, activity and stage moves."
        }
        actions={
          <div role="group" aria-label="Whose follow-ups" className="inline-flex rounded-[9px] border border-border bg-surface-2 p-0.5 text-xs font-medium">
            {[
              { key: false, label: "Everyone" },
              { key: true, label: "Mine" },
            ].map((o) => (
              <button
                key={o.label}
                type="button"
                aria-pressed={mine === o.key}
                onClick={() => setMine(o.key)}
                className={cx("rounded-[7px] px-2.5 py-1", mine === o.key ? "bg-surface text-fg shadow-[var(--lift)]" : "text-fg-3 hover:text-fg")}
              >
                {o.label}
              </button>
            ))}
          </div>
        }
        testId="follow-ups"
      >
        {error && <ErrorNote error={error} />}
        {!data && !error && <Skeleton rows={3} />}
        {data && groups.length === 0 && <Empty>Nothing to follow up. Every opportunity has an owned, dated next action.</Empty>}
        {groups.length > 0 && (
          <div className="space-y-4">
            {groups.map((g) => (
              <FlagGroup key={g.kind} {...g} perGroup={perGroup} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
