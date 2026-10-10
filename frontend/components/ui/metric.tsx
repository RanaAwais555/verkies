import type { ReactNode } from "react";

import { cx } from "@/components/ui/cx";

const TONE = { neutral: "text-fg", accent: "text-accent-text", red: "text-bad", amber: "text-warn", green: "text-ok" };

export type Metric = { label: string; value: ReactNode; hint?: ReactNode; tone?: keyof typeof TONE; icon?: ReactNode };

/**
 * A row of headline numbers on one surface, divided by hairlines rather than boxed one by one.
 * Every value is a real count from the API, never an estimate.
 */
export function MetricStrip({ metrics, className }: { metrics: Metric[]; className?: string }) {
  return (
    <section className={cx("tray grid overflow-hidden rounded-[14px] border border-border/80 bg-surface sm:grid-cols-2 lg:grid-cols-[repeat(auto-fit,minmax(180px,1fr))]", className)}>
      {metrics.map((m, i) => (
        <div key={m.label} className={cx("flex min-w-0 flex-col gap-1.5 px-5 py-4", i > 0 && "border-t border-grid sm:border-t-0 sm:shadow-[inset_1px_0_0_var(--border)]")}>
          <span className="flex items-center gap-2 text-xs text-fg-3">
            {m.icon}
            {m.label}
          </span>
          <span className={cx("tabular text-[26px] font-semibold leading-none tracking-[-0.02em]", TONE[m.tone ?? "neutral"])}>{m.value}</span>
          {m.hint && <span className="text-xs text-fg-3">{m.hint}</span>}
        </div>
      ))}
    </section>
  );
}
