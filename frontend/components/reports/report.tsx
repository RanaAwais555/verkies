"use client";

import { ArrowRight, Info } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";

import { Empty, Panel } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { money } from "@/lib/format";
import type { FunnelStep, ReportCell, ReportFigure, ReportMoney, ReportTable } from "@/lib/types";

/** A figure's value in its unit. Null is Unknown: there was nothing to measure, which is not zero. */
export function formatFigure(f: Pick<ReportFigure, "value" | "unit" | "currency">): string {
  if (f.value === null) return "Unknown";
  switch (f.unit) {
    case "money":
      return money(f.value, f.currency ?? "GBP");
    case "percent":
      return `${f.value.toLocaleString("en-GB", { maximumFractionDigits: 1 })}%`;
    case "days":
      return `${f.value.toLocaleString("en-GB", { maximumFractionDigits: 1 })} ${f.value === 1 ? "day" : "days"}`;
    case "score":
      return f.value.toLocaleString("en-GB", { maximumFractionDigits: 1 });
    default:
      return f.value.toLocaleString("en-GB");
  }
}

function amounts(list: ReportMoney[]): string {
  return list.length === 0 ? "—" : list.map((m) => money(m.amount, m.currency)).join(" + ");
}

function cellText(cell: ReportCell, column: string): string {
  if (cell === null) return column === "Win rate" || column === "Probability" ? "Unknown" : "—";
  if (Array.isArray(cell)) return amounts(cell);
  if (typeof cell === "number") return column === "Win rate" || column === "Probability" ? `${cell}%` : cell.toLocaleString("en-GB");
  return cell;
}

/** "How it's counted": the rule behind a number, one click away, so every figure can be checked. */
function Definition({ text, className }: { text: string; className?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className={className}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1 text-[11.5px] text-fg-3 hover:text-fg"
      >
        <Info aria-hidden className="h-3 w-3" />
        How it&apos;s counted
      </button>
      {open && (
        <span id={id} className="mt-1 block text-xs leading-relaxed text-fg-2">
          {text}
        </span>
      )}
    </span>
  );
}

export function FigureGrid({ figures }: { figures: ReportFigure[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4" data-testid="figures">
      {figures.map((f) => (
        <section key={f.key} className="lift flex min-w-0 flex-col gap-1 rounded-xl border border-border/80 bg-surface p-4" data-testid={`figure-${f.key}`}>
          <h3 className="text-[12.5px] font-medium text-fg-2">{f.label}</h3>
          <p className={cx("tabular text-[22px] font-semibold tracking-[-0.02em]", f.value === null ? "text-fg-3" : "text-fg")}>{formatFigure(f)}</p>
          {f.detail && <p className="text-xs text-fg-3">{f.detail}</p>}
          <div className="mt-auto flex flex-wrap items-center justify-between gap-x-3 gap-y-1 pt-1">
            <Definition text={f.definition} />
            {f.href && (
              <Link href={f.href} className="inline-flex items-center gap-1 text-[11.5px] font-medium text-accent-text hover:underline">
                See them
                <ArrowRight aria-hidden className="h-3 w-3" />
              </Link>
            )}
          </div>
        </section>
      ))}
    </div>
  );
}

/**
 * §13's conversion funnel. One hue: the bars measure one thing (how many companies reached each
 * step), so colour carries no extra meaning. Each step shows its count and the share of the step
 * before it; the rule for every step is listed under the chart.
 */
export function Funnel({ steps }: { steps: FunnelStep[] }) {
  const first = steps[0]?.count ?? 0;
  return (
    <Panel
      title="Conversion funnel"
      description="Companies first researched in the period, by the furthest step each reached."
      footer={
        <details className="px-5 py-3 text-xs text-fg-2">
          <summary className="cursor-pointer text-fg-3 hover:text-fg">How each step is counted</summary>
          <dl className="mt-2 grid gap-x-3 gap-y-1.5 sm:grid-cols-[7rem_minmax(0,1fr)]">
            {steps.map((s) => (
              <div key={s.key} className="contents">
                <dt className="font-medium text-fg">{s.label}</dt>
                <dd>{s.definition}</dd>
              </div>
            ))}
          </dl>
        </details>
      }
      testId="funnel"
    >
      {first === 0 ? (
        <Empty>No company was researched in this period.</Empty>
      ) : (
        <ol className="space-y-2">
          {steps.map((s, i) => {
            const previous = i === 0 ? null : steps[i - 1].count;
            const share = previous ? Math.round((100 * s.count) / previous) : null;
            return (
              <li key={s.key} className="grid grid-cols-[6.5rem_minmax(0,1fr)_4.5rem] items-center gap-3 text-[13px] sm:grid-cols-[7.5rem_minmax(0,1fr)_6rem]">
                <span className="text-fg-2">{s.label}</span>
                <span className="h-6 rounded-md bg-track" aria-hidden>
                  <span
                    className="block h-full rounded-md bg-accent transition-[width] duration-500 ease-spring"
                    style={{ width: `${Math.max((100 * s.count) / first, s.count ? 1.5 : 0)}%` }}
                  />
                </span>
                <span className="tabular text-right">
                  <span className="font-semibold text-fg">{s.count}</span>
                  {i > 0 && <span className="text-xs text-fg-3"> · {previous === 0 ? "—" : `${share}%`}</span>}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}

/**
 * A breakdown. With one numeric column it is drawn as labelled bars (one hue, length = the value);
 * with several columns it is a plain table, so every number can be read exactly.
 */
export function ReportTableCard({ table, empty = "Nothing to show for this period." }: { table: ReportTable; empty?: string }) {
  const single = table.columns.length === 1 && table.rows.every((r) => typeof r.values[0] === "number");
  const max = single ? Math.max(1, ...table.rows.map((r) => r.values[0] as number)) : 1;
  return (
    <Panel title={table.label} description={<Definition text={table.definition} />} testId={`table-${table.key}`}>
      {table.rows.length === 0 ? (
        <Empty>{empty}</Empty>
      ) : single ? (
        <ul className="space-y-1.5">
          {table.rows.map((r) => {
            const value = r.values[0] as number;
            const label = r.href ? (
              <Link href={r.href} className="truncate text-fg-2 hover:text-accent-text hover:underline">
                {r.label}
              </Link>
            ) : (
              <span className="truncate text-fg-2">{r.label}</span>
            );
            return (
              <li key={r.label} className="grid grid-cols-[minmax(0,13rem)_minmax(0,1fr)_3rem] items-center gap-3 text-[13px]">
                {label}
                <span className="h-2.5 rounded-full bg-track" aria-hidden>
                  <span className="block h-full rounded-full bg-accent" style={{ width: `${(100 * value) / max}%` }} />
                </span>
                <span className="tabular text-right font-medium text-fg">{value.toLocaleString("en-GB")}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="-mx-5 overflow-x-auto px-5">
          <table className={cx("w-full text-[13px]", table.columns.length > 3 && "min-w-[40rem]")}>
            <thead>
              <tr className="border-b border-grid text-left text-xs text-fg-3">
                <th scope="col" className="py-2 pr-3 font-medium">
                  <span className="sr-only">Name</span>
                </th>
                {table.columns.map((c) => (
                  <th key={c} scope="col" className="py-2 pl-3 text-right font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-grid">
              {table.rows.map((r) => (
                <tr key={r.label}>
                  <th scope="row" className="py-2 pr-3 text-left font-medium text-fg">
                    {r.href ? (
                      <Link href={r.href} className="hover:text-accent-text hover:underline">
                        {r.label}
                      </Link>
                    ) : (
                      r.label
                    )}
                  </th>
                  {r.values.map((v, i) => (
                    <td key={table.columns[i]} className={cx("tabular py-2 pl-3 text-right", v === null ? "text-fg-3" : "text-fg-2")}>
                      {cellText(v, table.columns[i])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {table.note && <p className="mt-3 text-xs text-fg-3">{table.note}</p>}
    </Panel>
  );
}
