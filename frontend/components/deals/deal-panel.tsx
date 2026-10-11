"use client";

import { ExternalLink, Save, X } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { NewTaskForm } from "@/components/crm/tasks";
import { Badge, Button, ErrorNote, Field, IconButton, inputClass } from "@/components/ui";
import { api } from "@/lib/client";
import { formatDate, money } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Deal, PipelineStage, TeamMember } from "@/lib/types";

/** Say why a deal was lost (§13) before it moves to a lost stage. */
export function LostForm({
  deal,
  stage,
  reasons,
  onDone,
  onCancel,
}: {
  deal: Deal;
  stage: PipelineStage;
  reasons: { key: string; label: string }[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const moved = await run(() =>
      api(`/deals/${deal.id}/move`, {
        method: "POST",
        body: { stage_id: stage.id, lost_reason: data.get("reason"), lost_note: String(data.get("note") ?? "").trim() || null },
      }).then(() => true),
    );
    if (moved) onDone();
  }

  return (
    <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-bad/30 bg-bad-soft p-3.5" data-testid="lost-form">
      <p className="text-[13px] font-medium text-fg">
        Why was {deal.account_name} lost? It moves to {stage.name}.
      </p>
      <Field label="Lost reason">
        <select name="reason" required defaultValue="" className={inputClass}>
          <option value="" disabled>
            Choose a reason
          </option>
          {reasons.map((r) => (
            <option key={r.key} value={r.key}>
              {r.label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Note (optional)">
        <input name="note" maxLength={2000} className={inputClass} />
      </Field>
      <ErrorNote error={error} />
      <div className="flex gap-2">
        <Button type="submit" variant="danger" busy={busy}>
          Mark as lost
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** A deal's details beside the board: edit value, close date, owner and probability; set the next task. */
export function DealPanel({ deal, onClose, onChange }: { deal: Deal; onClose: () => void; onChange: () => void }) {
  const { data: team } = useApi<TeamMember[]>("/team");
  const { busy, error, run } = useAction();
  const [adding, setAdding] = useState(false);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const value = String(data.get("value") ?? "").trim();
    const probability = String(data.get("probability") ?? "").trim();
    const saved = await run(() =>
      api(`/deals/${deal.id}`, {
        method: "PATCH",
        body: {
          name: String(data.get("name") ?? "").trim() || deal.name,
          value: value === "" ? null : value,
          currency: String(data.get("currency") ?? "GBP").trim() || "GBP",
          expected_close: String(data.get("close") ?? "") || null,
          owner_id: data.get("owner") || null,
          // Empty means "use the stage's default".
          probability: probability === "" ? null : probability,
        },
      }).then(() => true),
    );
    if (saved) onChange();
  }

  return (
    <aside aria-label={`Deal: ${deal.name}`} className="lift animate-slide-in space-y-4 rounded-xl border border-border/80 bg-surface p-5" data-testid="deal-panel">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-[16px] font-semibold text-fg">{deal.account_name}</h2>
          <p className="text-xs text-fg-3">
            {deal.stage_name} · since {formatDate(deal.stage_entered_at)} · {money(deal.weighted_value, deal.currency, "not weighted")}
            {deal.weighted_value !== null && " weighted"}
          </p>
        </div>
        <IconButton label="Close the deal panel" onClick={onClose}>
          <X className="h-4 w-4" />
        </IconButton>
      </div>
      {deal.outcome === "lost" && deal.lost_reason && (
        <Badge tone="red">
          Lost: {deal.lost_reason.replaceAll("_", " ")}
          {deal.lost_note ? ` · ${deal.lost_note}` : ""}
        </Badge>
      )}

      <form key={deal.id + deal.stage_id} onSubmit={save} className="space-y-3">
        <Field label="Deal name">
          <input name="name" defaultValue={deal.name} maxLength={200} className={inputClass} />
        </Field>
        <div className="grid grid-cols-[minmax(0,1fr)_88px] gap-2">
          <Field label="Value" hint="Leave empty while it is unknown.">
            <input name="value" type="number" min={0} step="0.01" defaultValue={deal.value ?? ""} className={inputClass} />
          </Field>
          <Field label="Currency">
            <input name="currency" defaultValue={deal.currency} maxLength={3} pattern="[A-Za-z]{3}" className={`${inputClass} uppercase`} />
          </Field>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Expected close">
            <input name="close" type="date" defaultValue={deal.expected_close ?? ""} className={inputClass} />
          </Field>
          <Field label="Probability (%)" hint={deal.probability_is_stage_default ? "Stage default; type to override." : "Set on this deal."}>
            <input
              name="probability"
              type="number"
              min={0}
              max={100}
              step="1"
              defaultValue={deal.probability_is_stage_default ? "" : (deal.probability ?? "")}
              placeholder={deal.probability === null ? "None" : String(deal.probability)}
              className={inputClass}
            />
          </Field>
        </div>
        <Field label="Owner">
          <select key={team ? "team" : "loading"} name="owner" defaultValue={deal.owner?.id ?? ""} className={inputClass}>
            <option value="">Nobody</option>
            {team?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </Field>
        <ErrorNote error={error} />
        <Button type="submit" variant="primary" busy={busy} icon={<Save className="h-4 w-4" />}>
          Save deal
        </Button>
      </form>

      <div className="space-y-2 border-t border-grid pt-4">
        <h3 className="text-[13px] font-semibold text-fg">Next task</h3>
        {deal.next_task ? (
          <p className="text-[13px] text-fg-2">
            {deal.next_task.title}
            <span className="text-fg-3">
              {" "}
              · {deal.next_task.owner_name ?? "nobody"} · {deal.next_task.due_at ? formatDate(deal.next_task.due_at) : "no date"}
            </span>
          </p>
        ) : (
          <p className="text-[13px] text-bad">No next task. Every open deal needs one.</p>
        )}
        {adding ? (
          <NewTaskForm
            accountId={deal.account_id}
            dealId={deal.id}
            submitLabel="Add next task"
            onCancel={() => setAdding(false)}
            onCreated={() => {
              setAdding(false);
              onChange();
            }}
          />
        ) : (
          <Button onClick={() => setAdding(true)}>Add next task</Button>
        )}
      </div>
      <Link href={`/accounts/${deal.account_id}`} className="inline-flex items-center gap-1.5 text-[13px] text-accent-text hover:underline">
        Open {deal.account_name}
        <ExternalLink aria-hidden className="h-3.5 w-3.5" />
      </Link>
    </aside>
  );
}
