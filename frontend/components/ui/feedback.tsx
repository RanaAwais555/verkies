import { CheckCircle2, CircleAlert, Inbox } from "lucide-react";
import type { ReactNode } from "react";

import { Spinner } from "@/components/ui/button";
import { cx } from "@/components/ui/cx";
import { ApiError } from "@/lib/client";

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <p className="flex items-center gap-2 py-2 text-[13px] text-fg-3" role="status">
      <Spinner /> {what}…
    </p>
  );
}

/** Placeholder rows while a list loads, so the layout does not jump when data arrives. */
export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3 py-1" aria-hidden>
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="h-3 rounded bg-[linear-gradient(90deg,var(--sunken)_25%,var(--surface-2)_50%,var(--sunken)_75%)] bg-[length:200%_100%] [animation:shimmer_1.1s_linear_infinite]"
          style={{ width: `${92 - ((i * 17) % 40)}%` }}
        />
      ))}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof ApiError || error instanceof Error ? error.message : "Something went wrong.";
  return (
    <p role="alert" className="flex items-start gap-2 rounded-[10px] border border-bad/30 bg-bad-soft px-3 py-2 text-[13px] text-bad">
      <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </p>
  );
}

export function Empty({ children, icon, action }: { children: ReactNode; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-[12px] border border-dashed border-border-strong px-4 py-8 text-center text-[13px] text-fg-3">
      <span className="grid h-9 w-9 place-items-center rounded-[10px] bg-sunken text-fg-3">{icon ?? <Inbox className="h-4 w-4" />}</span>
      <p>{children}</p>
      {action}
    </div>
  );
}

/** A positive confirmation after an action. */
export function Success({ children, testId, className }: { children: ReactNode; testId?: string; className?: string }) {
  return (
    <p role="status" data-testid={testId} className={cx("flex items-start gap-2 rounded-[10px] border border-ok/30 bg-ok-soft px-3 py-2 text-[13px] text-ok", className)}>
      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

/** A neutral explanatory note, e.g. why a section is empty or what a setting does. */
export function Note({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cx("text-xs leading-relaxed text-fg-3", className)}>{children}</p>;
}
