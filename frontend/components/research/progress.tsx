import { ErrorNote, Panel } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { label } from "@/lib/format";
import type { RunDetail } from "@/lib/types";

const DOT: Record<string, string> = {
  completed: "bg-ok",
  running: "animate-pulse bg-accent",
  failed: "bg-bad",
};

/** Live crawl progress while the worker runs; the page polls and replaces it with the brief. */
export function Progress({ run }: { run: RunDetail }) {
  return (
    <Panel title="Progress" primary>
      <div
        className="mb-4 h-2 overflow-hidden rounded-full bg-track"
        role="progressbar"
        aria-label="Research progress"
        aria-valuenow={run.progress_pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="h-full rounded-full bg-accent transition-[width] duration-500 ease-spring" style={{ width: `${run.progress_pct}%` }} />
      </div>
      <ol className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-5" data-testid="stages">
        {run.stages.map((s) => (
          <li key={s.stage} className="flex items-center gap-2 text-[13px]">
            <span aria-hidden className={cx("inline-block h-2 w-2 rounded-full", DOT[s.status] ?? "bg-border-strong")} />
            <span className="text-fg">{label(s.stage)}</span>
            <span className="text-xs text-fg-3">{s.status === "running" ? `${s.progress_pct}%` : label(s.status)}</span>
          </li>
        ))}
      </ol>
      {run.error && (
        <div className="mt-4">
          <ErrorNote error={new Error(run.error)} />
        </div>
      )}
    </Panel>
  );
}
