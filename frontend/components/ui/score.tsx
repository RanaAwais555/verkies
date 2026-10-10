import { cx } from "@/components/ui/cx";
import { label } from "@/lib/format";

/** A 0–100 score. Null is Unknown (no evidence), never zero. */
export function Score({ value, className }: { value: number | null | undefined; className?: string }) {
  if (value === null || value === undefined) {
    return (
      <span className={cx("text-fg-3", className)} title="Unknown: no evidence was found">
        Unknown
      </span>
    );
  }
  return <span className={cx("tabular font-mono", className)}>{Math.round(value)}</span>;
}

const BAND_SCORE: { min: number; cls: string }[] = [
  { min: 90, cls: "bg-bad-soft text-bad" },
  { min: 75, cls: "bg-accent-soft text-accent-text" },
  { min: 60, cls: "bg-ok-soft text-ok" },
  { min: 40, cls: "bg-sunken text-fg-2" },
  { min: 0, cls: "bg-bad-soft/60 text-fg-3" },
];

/** A compact score chip, coloured by band. Unknown shows a dash. */
export function ScoreChip({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    return (
      <span title="Unknown: no evidence" className="inline-grid h-[22px] min-w-[34px] place-items-center rounded-md bg-sunken px-1.5 text-xs text-fg-3">
        —
      </span>
    );
  }
  const cls = BAND_SCORE.find((b) => value >= b.min)!.cls;
  return (
    <span className={cx("tabular inline-grid h-[22px] min-w-[34px] place-items-center rounded-md px-1.5 font-mono text-[12.5px] font-semibold", cls)}>
      {Math.round(value)}
    </span>
  );
}

/** Bar colour follows the value; Unknown has no bar at all, so it can never read as a low score. */
function barTone(value: number): string {
  if (value >= 70) return "bg-ok";
  if (value >= 40) return "bg-accent";
  return "bg-fg-3";
}

export function ScoreBar({ name, value }: { name: string; value: number | null | undefined }) {
  return (
    <div className="grid grid-cols-[minmax(0,10rem)_1fr_3.5rem] items-center gap-3 text-[13px]">
      <span className="truncate text-fg-2">{label(name)}</span>
      <div className="h-[7px] overflow-hidden rounded-full bg-track">
        {value !== null && value !== undefined && (
          <div
            className={cx("h-full rounded-full transition-[width] duration-300 ease-spring", barTone(value))}
            style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
          />
        )}
      </div>
      <Score value={value} className="text-right text-[12.5px] font-medium" />
    </div>
  );
}
