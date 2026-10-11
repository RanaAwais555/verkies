"use client";

import { Columns3 } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type DragEvent } from "react";

import { DealCard, DRAG_TYPE } from "@/components/deals/deal-card";
import { DealPanel, LostForm } from "@/components/deals/deal-panel";
import { ForecastChart, ForecastStrip } from "@/components/deals/forecast";
import { Badge, controlClass, Empty, ErrorNote, PageHeader, Panel, Skeleton, Tabs } from "@/components/ui";
import { SaveViewButton } from "@/components/views/save-view";
import { cx } from "@/components/ui/cx";
import { api, withQuery } from "@/lib/client";
import { money } from "@/lib/format";
import { useAction, useApi, useTab } from "@/lib/hooks";
import type { Deal, Forecast, Pipeline, PipelineStage, Pipelines } from "@/lib/types";

const OUTCOME_TINT: Record<PipelineStage["outcome"], string> = {
  open: "bg-accent",
  won: "bg-ok",
  lost: "bg-bad",
  nurture: "bg-warn",
  inactive: "bg-fg-3",
};

function Column({
  stage,
  deals,
  stages,
  selected,
  onSelect,
  onMove,
}: {
  stage: PipelineStage;
  deals: Deal[];
  stages: PipelineStage[];
  selected: string | null;
  onSelect: (id: string) => void;
  onMove: (deal: Deal, stage: PipelineStage) => void;
}) {
  const [over, setOver] = useState(false);
  const total = deals.reduce((sum, d) => sum + (d.value ?? 0), 0);
  const unknown = deals.filter((d) => d.value === null).length;

  function drop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setOver(false);
    // The board looks the deal up by id; dropping it on its own column does nothing.
    const id = event.dataTransfer.getData(DRAG_TYPE);
    if (id) onMove({ id } as Deal, stage);
  }

  return (
    <section
      aria-label={`${stage.name}: ${deals.length} deals`}
      data-testid={`stage-${stage.key}`}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes(DRAG_TYPE)) {
          e.preventDefault();
          setOver(true);
        }
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      className={cx(
        "flex shrink-0 flex-col rounded-xl border bg-sunken/60 transition-[width,background-color,border-color] duration-200 ease-spring",
        // An empty stage stays a drop target but gives its room to stages that hold deals.
        deals.length ? "w-[264px]" : "w-[168px]",
        over ? "border-accent bg-accent-soft/40" : "border-border/60",
      )}
    >
      <header className="space-y-1 border-b border-grid px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span aria-hidden className={cx("h-2 w-2 rounded-full", OUTCOME_TINT[stage.outcome])} />
          <h2 className="min-w-0 flex-1 truncate text-[13px] font-semibold text-fg">{stage.name}</h2>
          <span className="tabular rounded-md bg-surface px-1.5 text-xs text-fg-2">{deals.length}</span>
        </div>
        <p className="tabular text-[11.5px] text-fg-3">
          {deals.length === 0 ? "No deals" : money(total, deals[0].currency)}
          {unknown > 0 && ` + ${unknown} unknown`}
          {stage.probability !== null && stage.outcome === "open" && ` · ${stage.probability}%`}
        </p>
      </header>
      <div className="flex min-h-24 flex-1 flex-col gap-2 p-2">
        {deals.map((deal) => (
          <DealCard
            key={deal.id}
            deal={deal}
            stages={stages}
            selected={selected === deal.id}
            onSelect={() => onSelect(deal.id)}
            onMove={(target) => onMove(deal, target)}
          />
        ))}
      </div>
    </section>
  );
}

/** Board filters kept in the address: a minimum value and "closing this month". The forecast above ignores them. */
type CardFilter = { minValue: number | null; closingThisMonth: boolean };

function matches(deal: Deal, { minValue, closingThisMonth }: CardFilter): boolean {
  if (minValue !== null && (deal.value === null || deal.value < minValue)) return false;
  if (closingThisMonth) {
    const now = new Date();
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    if (!deal.expected_close?.startsWith(month)) return false;
  }
  return true;
}

function Board({
  pipeline,
  owner,
  filter,
  lostReasons,
}: {
  pipeline: Pipeline;
  owner: string;
  filter: CardFilter;
  lostReasons: { key: string; label: string }[];
}) {
  const deals = useApi<Deal[]>(withQuery("/deals", { pipeline_id: pipeline.id, owner, status: "all" }));
  const forecast = useApi<Forecast[]>(withQuery("/deals/forecast", { pipeline_id: pipeline.id }));
  const [selected, setSelected] = useState<string | null>(null);
  const [losing, setLosing] = useState<{ deal: Deal; stage: PipelineStage } | null>(null);
  const action = useAction();

  async function refresh() {
    await Promise.all([deals.mutate(), forecast.mutate()]);
  }

  async function move(dealRef: Deal, stage: PipelineStage) {
    const deal = deals.data?.find((d) => d.id === dealRef.id);
    if (!deal || deal.stage_id === stage.id) return;
    if (stage.outcome === "lost") {
      setLosing({ deal, stage });
      return;
    }
    if (await action.run(() => api(`/deals/${deal.id}/move`, { method: "POST", body: { stage_id: stage.id } }).then(() => true))) await refresh();
  }

  const current = deals.data?.find((d) => d.id === selected) ?? null;
  const shown = deals.data?.filter((d) => matches(d, filter)) ?? [];
  const filtered = filter.minValue !== null || filter.closingThisMonth;
  return (
    <div className="space-y-4">
      {forecast.data?.map((f) => (
        <ForecastStrip key={f.currency} forecast={f} />
      ))}
      {forecast.data?.[0] && <ForecastChart forecast={forecast.data[0]} />}
      <ErrorNote error={deals.error ?? action.error} />
      {losing && (
        <LostForm
          deal={losing.deal}
          stage={losing.stage}
          reasons={lostReasons}
          onCancel={() => setLosing(null)}
          onDone={async () => {
            setLosing(null);
            await refresh();
          }}
        />
      )}
      {!deals.data && !deals.error && <Skeleton rows={6} />}
      {deals.data?.length === 0 && (
        <Panel>
          <Empty icon={<Columns3 className="h-4 w-4" />}>
            No deals in {pipeline.name} yet. Open one from an opportunity on its account page.
          </Empty>
        </Panel>
      )}
      {deals.data && deals.data.length > 0 && filtered && shown.length === 0 && (
        <Panel>
          <Empty icon={<Columns3 className="h-4 w-4" />}>No deal in {pipeline.name} matches these filters.</Empty>
        </Panel>
      )}
      {deals.data && shown.length > 0 && (
        <div className={cx("grid grid-cols-[minmax(0,1fr)] items-start gap-4", current && "xl:grid-cols-[minmax(0,1fr)_360px]")}>
          {/* min-w-0: the board scrolls inside its own box instead of widening the page. */}
          <div className="-mx-1 min-w-0 overflow-x-auto px-1 pb-2" data-testid="board">
            <div className="flex gap-3">
              {pipeline.stages.map((stage) => (
                <Column
                  key={stage.id}
                  stage={stage}
                  stages={pipeline.stages}
                  deals={shown.filter((d) => d.stage_id === stage.id)}
                  selected={selected}
                  onSelect={setSelected}
                  onMove={move}
                />
              ))}
            </div>
          </div>
          {current && (
            <div className="xl:sticky xl:top-20">
              <DealPanel deal={current} onClose={() => setSelected(null)} onChange={refresh} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function PipelinePage() {
  const { data, error } = useApi<Pipelines>("/pipelines");
  const [tab, setTab] = useTab("new_business");
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const owner = ["me", "unassigned"].includes(params.get("owner") ?? "") ? params.get("owner")! : "";
  const minValue = Number(params.get("min_value")) > 0 ? Number(params.get("min_value")) : null;
  const closingThisMonth = params.get("closing") === "this_month";

  // Filters live in the address, so a saved view such as "High Value Pipeline" can open them.
  function set(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }
  const pipeline = data?.pipelines.find((p) => p.key === tab) ?? data?.pipelines[0];

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Revenue"
        title="Pipeline"
        description="Every deal by stage. Drag a card, or use its Move menu. A deal's value stays Unknown until someone enters it."
        actions={
          <>
            <select value={owner} onChange={(e) => set({ owner: e.target.value || null })} aria-label="Deal owner" className={`${controlClass} w-40`}>
              <option value="">Everyone&apos;s deals</option>
              <option value="me">My deals</option>
              <option value="unassigned">Unassigned</option>
            </select>
            <SaveViewButton suggestedName="Pipeline" />
          </>
        }
      />
      {error && <ErrorNote error={error} />}
      {!data && !error && <Skeleton rows={4} />}
      {data && pipeline && (
        <>
          <Tabs label="Pipelines" tabs={data.pipelines.map((p) => ({ key: p.key, label: p.name }))} active={pipeline.key} onChange={setTab} />
          {(minValue !== null || closingThisMonth) && (
            <div className="flex flex-wrap items-center gap-2 text-[13px]" data-testid="board-filters">
              <span className="text-fg-3">Showing deals</span>
              {minValue !== null && <Badge tone="accent">worth {minValue.toLocaleString("en-GB")} or more</Badge>}
              {closingThisMonth && <Badge tone="accent">expected to close this month</Badge>}
              <button
                type="button"
                onClick={() => set({ min_value: null, closing: null })}
                className="text-xs font-medium text-accent-text hover:underline"
              >
                Clear filters
              </button>
            </div>
          )}
          <Board key={pipeline.id} pipeline={pipeline} owner={owner} filter={{ minValue, closingThisMonth }} lostReasons={data.lost_reasons} />
        </>
      )}
    </div>
  );
}
