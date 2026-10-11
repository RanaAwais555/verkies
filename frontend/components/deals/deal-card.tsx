"use client";

import { AlertTriangle, CalendarClock, GripVertical } from "lucide-react";
import Link from "next/link";
import type { DragEvent } from "react";

import { BandBadge } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { formatDate, initials, isOverdue, money, relativeDate } from "@/lib/format";
import type { Deal, PipelineStage } from "@/lib/types";

export const DRAG_TYPE = "application/x-vros-deal";

/**
 * A deal on the board (master context §12's kanban card): company, opportunity, value, owner,
 * priority, next task, last activity, days in stage and probability. It can be dragged to another
 * column, or moved with the "Move to" menu, which works without a mouse.
 */
export function DealCard({
  deal,
  stages,
  selected,
  onSelect,
  onMove,
}: {
  deal: Deal;
  stages: PipelineStage[];
  selected: boolean;
  onSelect: () => void;
  onMove: (stage: PipelineStage) => void;
}) {
  function dragStart(event: DragEvent<HTMLElement>) {
    event.dataTransfer.setData(DRAG_TYPE, deal.id);
    event.dataTransfer.effectAllowed = "move";
  }
  const overdue = deal.next_task && isOverdue(deal.next_task.due_at);

  return (
    <article
      draggable
      onDragStart={dragStart}
      data-testid="deal"
      className={cx(
        "group relative cursor-grab space-y-2.5 rounded-xl border bg-surface p-3 text-[13px] shadow-[var(--lift)] transition-[border-color,transform] duration-200 ease-spring active:cursor-grabbing",
        selected ? "border-accent" : "border-border/80 hover:border-border-strong",
      )}
    >
      <div className="flex items-start gap-2">
        <GripVertical aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-fg-3 opacity-0 transition-opacity group-hover:opacity-100" />
        <div className="min-w-0 flex-1">
          <button type="button" onClick={onSelect} className="block max-w-full truncate text-left font-semibold text-fg hover:text-accent-text" title={deal.name}>
            {deal.account_name}
          </button>
          <p className="truncate text-xs text-fg-3" title={deal.opportunity_name ?? deal.name}>
            {deal.opportunity_name ?? deal.name}
          </p>
        </div>
        <span
          aria-label={deal.owner?.name ? `Owner ${deal.owner.name}` : "No owner"}
          title={deal.owner?.name ?? "No owner"}
          className={cx(
            "grid h-6 w-6 shrink-0 place-items-center rounded-full text-[10px] font-semibold",
            deal.owner ? "bg-accent-soft text-accent-text" : "border border-dashed border-border-strong text-fg-3",
          )}
        >
          {deal.owner?.name ? initials(deal.owner.name) : "?"}
        </span>
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-x-2">
        <span className={cx("tabular text-[15px] font-semibold", deal.value === null ? "text-fg-3" : "text-fg")}>
          {money(deal.value, deal.currency)}
        </span>
        <span className="tabular text-xs text-fg-3" title={deal.probability_is_stage_default ? "The stage's default probability" : "Set on this deal"}>
          {deal.probability === null ? "No probability" : `${deal.probability}%`}
          {deal.weighted_value !== null && ` · ${money(deal.weighted_value, deal.currency)} weighted`}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <BandBadge band={deal.priority_band} />
        {deal.expected_close && (
          <span className="inline-flex items-center gap-1 text-xs text-fg-3">
            <CalendarClock aria-hidden className="h-3 w-3" />
            closes {formatDate(deal.expected_close)}
          </span>
        )}
      </div>

      {deal.next_task ? (
        <p className={cx("truncate text-xs", overdue ? "font-medium text-bad" : "text-fg-2")} title={deal.next_task.title}>
          Next: {deal.next_task.title}
          {deal.next_task.due_at && ` · ${formatDate(deal.next_task.due_at)}`}
        </p>
      ) : null}
      {deal.requires_attention.length > 0 && (
        <p className="flex items-start gap-1.5 text-xs text-bad">
          <AlertTriangle aria-hidden className="mt-px h-3.5 w-3.5 shrink-0" />
          {deal.requires_attention.join(", ")}
        </p>
      )}

      <div className="flex items-center justify-between gap-2 border-t border-grid pt-2 text-[11.5px] text-fg-3">
        <span>
          {deal.days_in_stage} {deal.days_in_stage === 1 ? "day" : "days"} in stage
          {deal.last_activity_at && ` · active ${relativeDate(deal.last_activity_at).toLowerCase()}`}
        </span>
        <select
          aria-label={`Move ${deal.account_name} to`}
          value=""
          onChange={(e) => {
            const stage = stages.find((s) => s.id === e.target.value);
            if (stage) onMove(stage);
          }}
          className="h-6 max-w-[96px] rounded-md border border-border bg-surface-2 px-1 text-[11.5px] text-fg-2"
        >
          <option value="">Move to…</option>
          {stages
            .filter((s) => s.id !== deal.stage_id)
            .map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
        </select>
      </div>
      <Link href={`/accounts/${deal.account_id}`} className="sr-only">
        Open {deal.account_name}
      </Link>
    </article>
  );
}
