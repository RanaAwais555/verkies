import type { ReactNode } from "react";

import { cx } from "@/components/ui/cx";
import { label } from "@/lib/format";
import type { ClaimClass } from "@/lib/types";

const TONES = {
  neutral: "bg-sunken text-fg-2",
  green: "bg-ok-soft text-ok",
  amber: "bg-warn-soft text-warn",
  red: "bg-bad-soft text-bad",
  blue: "bg-info-soft text-info",
  purple: "bg-violet-soft text-violet",
  accent: "bg-accent-soft text-accent-text",
};

export type Tone = keyof typeof TONES;

export function Badge({ tone = "neutral", children, title, className }: { tone?: Tone; children: ReactNode; title?: string; className?: string }) {
  return (
    <span title={title} className={cx("inline-flex h-[21px] items-center gap-1 whitespace-nowrap rounded-md px-2 text-[11.5px] font-medium", TONES[tone], className)}>
      {children}
    </span>
  );
}

const BAND_TONE: Record<string, Tone> = { hot: "red", high: "amber", qualified: "green", monitor: "blue", reject: "neutral" };

/** The priority band from the score. Prefixed so it never reads like an action next to Reject. */
export function BandBadge({ band }: { band: string | null }) {
  if (!band) return <Badge title="Priority band: Unknown">Band: Unknown</Badge>;
  return (
    <Badge tone={BAND_TONE[band] ?? "neutral"} title="Priority band from the score">
      Band: {label(band)}
    </Badge>
  );
}

const STATUS_TONE: Record<string, Tone> = {
  queued: "neutral",
  running: "blue",
  retrying: "blue",
  completed: "green",
  failed: "red",
  cancelled: "neutral",
  pending: "amber",
  approved: "green",
  rejected: "red",
  open: "blue",
  in_progress: "blue",
  done: "green",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{label(status)}</Badge>;
}

/**
 * Fact, inference or recommendation, told apart by shape as well as colour: a solid square for a
 * fact, an open ring and dashed outline for an inference, an arrow for a recommendation.
 */
export function ClaimTag({ kind }: { kind: ClaimClass }) {
  const styles = {
    fact: "bg-ok-soft text-ok",
    inference: "border border-dashed border-warn/70 text-warn",
    recommendation: "bg-accent-soft text-accent-text",
  }[kind];
  const mark = {
    fact: <span aria-hidden className="h-1.5 w-1.5 rounded-[1px] bg-current" />,
    inference: <span aria-hidden className="h-1.5 w-1.5 rounded-full border-[1.5px] border-current" />,
    recommendation: <span aria-hidden className="h-0 w-0 border-y-[3.5px] border-l-[5px] border-y-transparent border-l-current" />,
  }[kind];
  return (
    <span className={cx("inline-flex h-5 shrink-0 items-center gap-1.5 rounded-md px-1.5 text-[11px] font-semibold", styles)}>
      {mark}
      {label(kind)}
    </span>
  );
}
