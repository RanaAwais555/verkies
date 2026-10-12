"use client";

import { GraduationCap } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Empty, ErrorNote, Note, PageHeader, Panel, Skeleton, Table, Tabs } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { formatDate, money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { WinLoss, WinLossGroup } from "@/lib/types";

const PERIODS = [
  { key: "6", label: "Last 6 months" },
  { key: "12", label: "Last 12 months" },
  { key: "24", label: "Last 2 years" },
  { key: "0", label: "All time" },
];

function percent(rate: number) {
  return `${Math.round(rate * 100)}%`;
}

/** Win rate as a thin bar with the overall rate marked; no bar at all when there are too few deals. */
function RateMeter({ group, baseline, minSample }: { group: WinLossGroup; baseline: number | null; minSample: number }) {
  const title = `${group.label}: ${group.won} won of ${group.total} closed${group.win_rate === null ? "" : ` (${percent(group.win_rate)})`}`;
  if (group.win_rate === null)
    return (
      <span className="text-xs text-fg-3" title={`Fewer than ${minSample} closed deals`}>
        Too few to learn from
      </span>
    );
  return (
    <div className="flex items-center gap-2.5" title={title}>
      <div className="relative h-[7px] w-32 shrink-0 overflow-hidden rounded-full bg-track" role="img" aria-label={title}>
        <div className="h-full rounded-full bg-accent" style={{ width: `${group.win_rate * 100}%` }} />
        {baseline !== null && <div aria-hidden className="absolute inset-y-[-2px] w-px bg-fg-2" style={{ left: `${baseline * 100}%` }} />}
      </div>
      <span className="tabular w-10 text-right text-[12.5px] font-medium text-fg">{percent(group.win_rate)}</span>
    </div>
  );
}

function Value({ group }: { group: WinLossGroup }) {
  if (group.won === 0) return <span className="text-fg-3">None won</span>;
  const known = group.won_value.map((m) => money(m.amount, m.currency)).join(" + ");
  return (
    <span className="tabular text-fg-2">
      {known || "Value unknown"}
      {known && group.won_unknown_value > 0 && <span className="block text-xs text-fg-3">and {group.won_unknown_value} without a value</span>}
    </span>
  );
}

function GroupTable({ groups, baseline, minSample, testId }: { groups: WinLossGroup[]; baseline: number | null; minSample: number; testId?: string }) {
  return (
    <Table testId={testId}>
      <thead>
        <tr>
          <th>Group</th>
          <th className="text-right">Won</th>
          <th className="text-right">Lost</th>
          <th>Win rate</th>
          <th>Value won</th>
          <th className="text-right">Days to win</th>
        </tr>
      </thead>
      <tbody>
        {groups.map((g) => (
          <tr key={g.label} data-testid="win-loss-row">
            <td className={cx("min-w-[10rem]", g.label === "Unknown" ? "text-fg-3" : "font-medium text-fg")}>{g.label}</td>
            <td className="tabular text-right text-fg-2">{g.won}</td>
            <td className="tabular text-right text-fg-2">{g.lost}</td>
            <td className="min-w-[13rem]">
              <RateMeter group={g} baseline={baseline} minSample={minSample} />
            </td>
            <td className="whitespace-nowrap">
              <Value group={g} />
            </td>
            <td className="tabular text-right text-fg-2">{g.avg_days_to_win === null ? "—" : Math.round(g.avg_days_to_win)}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export default function LearningPage() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const months = params.get("months") ?? "12";
  const { data, error } = useApi<WinLoss>(`/learning/win-loss?months=${months}`);

  function setMonths(key: string) {
    const next = new URLSearchParams(params);
    if (key === "12") next.delete("months");
    else next.set("months", key);
    const q = next.toString();
    router.replace(q ? `${pathname}?${q}` : pathname, { scroll: false });
  }

  const baseline = data?.overall.win_rate ?? null;
  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Learning"
        title="Win/loss analysis"
        description="What the deals you won and lost had in common, from what was true when each one closed. Every figure shows how many deals it rests on; small groups get no win rate."
      />
      <Tabs label="Period" tabs={PERIODS} active={months} onChange={setMonths} />
      {error ? (
        <ErrorNote error={error} />
      ) : !data ? (
        <Skeleton rows={8} />
      ) : data.overall.total === 0 ? (
        <Panel>
          <Empty icon={<GraduationCap className="h-4 w-4" />}>No deals were won or lost in this period, so there is nothing to learn from yet.</Empty>
        </Panel>
      ) : (
        <>
          <Panel
            title="All closed deals"
            description={data.since ? `Closed since ${formatDate(data.since)}.` : "Every deal ever closed."}
            testId="win-loss-overall"
          >
            <div className="flex flex-wrap items-end gap-x-10 gap-y-3">
              <div>
                <p className="text-xs text-fg-3">Win rate</p>
                <p className="tabular text-[26px] font-semibold text-fg">{baseline === null ? "Too few" : percent(baseline)}</p>
                <p className="text-xs text-fg-3">
                  {data.overall.won} won, {data.overall.lost} lost
                </p>
              </div>
              <div>
                <p className="text-xs text-fg-3">Value won</p>
                <p className="text-[15px] font-medium">
                  <Value group={data.overall} />
                </p>
              </div>
              <div>
                <p className="text-xs text-fg-3">Average days to win</p>
                <p className="tabular text-[15px] font-medium text-fg">
                  {data.overall.avg_days_to_win === null ? "—" : Math.round(data.overall.avg_days_to_win)}
                </p>
              </div>
            </div>
            <p className="mt-3 text-xs text-fg-3">
              The line on each bar marks this overall win rate. A group needs {data.min_sample} closed deals before it gets a win rate.
            </p>
            {data.captured_late > 0 && (
              <Note className="mt-3">
                {data.captured_late} of these deals closed before VROS recorded outcomes; their facts are as recorded later, not at the close.
              </Note>
            )}
          </Panel>

          {data.dimensions.map((d) => (
            <Panel key={d.key} title={d.label} testId={`dimension-${d.key}`}>
              <GroupTable groups={d.groups} baseline={baseline} minSample={data.min_sample} />
            </Panel>
          ))}

          <Panel
            title="Buying signals"
            description="Deals with each signal in the six months before the close, against deals without it."
            testId="win-loss-signals"
          >
            {data.signals.length === 0 ? (
              <Empty>No closed deal had a dated buying signal.</Empty>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th>Signal</th>
                    <th>With it</th>
                    <th>Without it</th>
                  </tr>
                </thead>
                <tbody>
                  {data.signals.map((s) => (
                    <tr key={s.signal}>
                      <td className="min-w-[10rem] font-medium text-fg">{s.label}</td>
                      <td className="min-w-[15rem]">
                        <span className="mb-1 block text-xs text-fg-3">
                          {s.with_signal.won} won of {s.with_signal.total}
                        </span>
                        <RateMeter group={s.with_signal} baseline={baseline} minSample={data.min_sample} />
                      </td>
                      <td className="min-w-[15rem]">
                        <span className="mb-1 block text-xs text-fg-3">
                          {s.without_signal.won} won of {s.without_signal.total}
                        </span>
                        <RateMeter group={s.without_signal} baseline={baseline} minSample={data.min_sample} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Panel>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Why deals were lost" testId="win-loss-reasons">
              {data.lost_reasons.length === 0 ? (
                <Empty>No deal was lost in this period.</Empty>
              ) : (
                <ul className="divide-y divide-grid text-[13px]">
                  {data.lost_reasons.map((r) => (
                    <li key={r.reason} className="flex justify-between gap-3 py-2 first:pt-0 last:pb-0">
                      <span className="text-fg-2">{r.reason}</span>
                      <span className="tabular font-medium text-fg">{r.deals}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
            <Panel title="After feedback" description="Deals on accounts that had this feedback before the close." testId="win-loss-feedback">
              {data.feedback.length === 0 ? (
                <Empty>No feedback was given on these accounts before their deals closed.</Empty>
              ) : (
                <ul className="divide-y divide-grid text-[13px]">
                  {data.feedback.map((g) => (
                    <li key={g.label} className="flex flex-wrap items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
                      <span className="text-fg-2">
                        {g.label}{" "}
                        <span className="text-xs text-fg-3">
                          ({g.won} won, {g.lost} lost)
                        </span>
                      </span>
                      <RateMeter group={g} baseline={baseline} minSample={data.min_sample} />
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
