"use client";

import { Building2, CheckSquare, ClipboardCheck, Clock, FileSearch, ShieldAlert, Target, UserRound, type LucideIcon } from "lucide-react";

import { Empty, ErrorNote, Skeleton } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { formatDate, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { TimelineEvent } from "@/lib/types";

// The event type's first word picks an icon and a tint, so the eye can scan the rail by kind.
const KINDS: { match: string; icon: LucideIcon; tint: string }[] = [
  { match: "account", icon: Building2, tint: "var(--accent)" },
  { match: "lead", icon: Target, tint: "var(--violet)" },
  { match: "contact", icon: UserRound, tint: "var(--info)" },
  { match: "task", icon: CheckSquare, tint: "var(--ok)" },
  { match: "research", icon: FileSearch, tint: "var(--violet)" },
  { match: "opportunity", icon: Target, tint: "var(--accent)" },
  { match: "prospect", icon: ClipboardCheck, tint: "var(--ok)" },
  { match: "reject", icon: ShieldAlert, tint: "var(--bad)" },
];

function kindOf(eventType: string) {
  const key = eventType.toLowerCase();
  return KINDS.find((k) => key.includes(k.match)) ?? { icon: Clock, tint: "var(--fg-3)" };
}

/** Everything that happened on an account, newest first, on a vertical rail. */
export function Timeline({ accountId, limit = 500, testId = "timeline" }: { accountId: string; limit?: number; testId?: string }) {
  const { data, error } = useApi<TimelineEvent[]>(`/accounts/${accountId}/timeline?limit=${limit}`);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={6} />;
  if (data.length === 0) return <Empty>Nothing has happened on this account yet.</Empty>;
  return (
    <ol className="relative" data-testid={testId}>
      {data.map((e, i) => {
        const { icon: Icon, tint } = kindOf(e.event_type);
        return (
          <li key={e.id} className="grid grid-cols-[76px_20px_34px_minmax(0,1fr)] gap-x-3">
            <time dateTime={e.occurred_at} className="pt-2 text-right text-[11.5px] leading-tight text-fg-3">
              {formatDate(e.occurred_at)}
              <span className="block font-mono text-[10.5px]">{new Date(e.occurred_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</span>
            </time>
            <span aria-hidden className="relative flex justify-center">
              <span className={cx("absolute w-0.5 bg-grid", i === 0 ? "top-4 bottom-0" : i === data.length - 1 ? "top-0 h-4" : "inset-y-0")} />
              <span className="relative mt-3 h-2.5 w-2.5 rounded-full border-2 border-page" style={{ background: tint }} />
            </span>
            <span
              aria-hidden
              className="mt-0.5 grid h-[34px] w-[34px] place-items-center rounded-[10px] border"
              style={{ color: tint, background: `color-mix(in srgb, ${tint} 11%, var(--surface))`, borderColor: `color-mix(in srgb, ${tint} 24%, transparent)` }}
            >
              <Icon className="h-4 w-4" />
            </span>
            <div className="mb-3 min-w-0 rounded-xl border border-border bg-surface px-3.5 py-2.5 transition-colors hover:border-border-strong">
              <p className="text-[13px] leading-relaxed text-fg">{e.summary}</p>
              <p className="mt-0.5 text-xs text-fg-3">
                {label(e.event_type.replaceAll(".", "_"))} · {e.actor?.name ?? "VROS"}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
