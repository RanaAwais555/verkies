"use client";

import { Plus, Trash2, UserCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button, Checkbox, ErrorNote, Field, IconButton, inputClass } from "@/components/ui";
import { api } from "@/lib/client";
import { useAction, useApi } from "@/lib/hooks";
import type { Deal, TeamMember } from "@/lib/types";

type MilestoneDraft = { key: number; name: string; due: string };

/** Planned milestones for a new project: a name and an optional due date each. */
export function MilestoneRows({ rows, onChange }: { rows: MilestoneDraft[]; onChange: (rows: MilestoneDraft[]) => void }) {
  const [next, setNext] = useState(rows.length + 1);
  return (
    <fieldset className="space-y-2">
      <legend className="text-xs font-medium text-fg-2">Milestones (optional)</legend>
      {rows.map((row, i) => (
        <div key={row.key} className="grid grid-cols-[minmax(0,1fr)_9.5rem_auto] items-center gap-2">
          <input
            aria-label={`Milestone ${i + 1}`}
            value={row.name}
            onChange={(e) => onChange(rows.map((r) => (r.key === row.key ? { ...r, name: e.target.value } : r)))}
            placeholder="e.g. Designs signed off"
            maxLength={200}
            className={inputClass}
          />
          <input
            aria-label={`Milestone ${i + 1} due`}
            type="date"
            value={row.due}
            onChange={(e) => onChange(rows.map((r) => (r.key === row.key ? { ...r, due: e.target.value } : r)))}
            className={inputClass}
          />
          <IconButton label={`Remove milestone ${i + 1}`} onClick={() => onChange(rows.filter((r) => r.key !== row.key))}>
            <Trash2 className="h-4 w-4" />
          </IconButton>
        </div>
      ))}
      <Button
        className="h-7 px-2.5 text-xs"
        icon={<Plus className="h-3.5 w-3.5" />}
        onClick={() => {
          onChange([...rows, { key: next, name: "", due: "" }]);
          setNext(next + 1);
        }}
      >
        Add milestone
      </Button>
    </fieldset>
  );
}

export function milestonesOf(rows: MilestoneDraft[]) {
  return rows.filter((r) => r.name.trim()).map((r) => ({ name: r.name.trim(), due_date: r.due || null }));
}

/**
 * §14 Convert Opportunity → Client, from a won deal. The account keeps everything it has; it
 * becomes a customer with an account manager and, if wanted, a project to deliver the work.
 */
export function ConvertForm({ deal, onDone, onCancel }: { deal: Deal; onDone: () => void; onCancel?: () => void }) {
  const router = useRouter();
  const { data: team } = useApi<TeamMember[]>("/team");
  const { busy, error, run } = useAction();
  const [withProject, setWithProject] = useState(true);
  const [milestones, setMilestones] = useState<MilestoneDraft[]>([]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const manager = String(data.get("manager") ?? "") || null;
    const result = await run(() =>
      api<{ project_id: string | null }>(`/deals/${deal.id}/convert`, {
        method: "POST",
        body: {
          account_manager_id: manager,
          kickoff_task: data.get("kickoff") === "on",
          project: withProject
            ? {
                name: String(data.get("name") ?? "").trim() || null,
                owner_id: String(data.get("owner") ?? "") || null,
                start_date: String(data.get("start") ?? "") || null,
                target_date: String(data.get("target") ?? "") || null,
                milestones: milestonesOf(milestones),
              }
            : null,
        },
      }),
    );
    if (!result) return;
    onDone();
    if (result.project_id) router.push(`/projects/${result.project_id}`);
  }

  return (
    <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-ok/30 bg-ok-soft p-3.5" data-testid="convert-form">
      <p className="text-[13px] text-fg">
        <span className="font-medium">Make {deal.account_name} a client.</span>{" "}
        <span className="text-fg-2">It stays the same account, with its people, deals, emails and history.</span>
      </p>
      <Field label="Account manager">
        <select key={team ? "team" : "loading"} name="manager" defaultValue={deal.owner?.id ?? ""} className={inputClass}>
          <option value="">Not decided yet</option>
          {team?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </Field>
      <Checkbox label="Start a project for this work" checked={withProject} onChange={(e) => setWithProject(e.target.checked)} />
      {withProject && (
        <div className="space-y-3 border-l-2 border-ok/30 pl-3">
          <Field label="Project name">
            <input name="name" defaultValue={deal.name} maxLength={200} className={inputClass} />
          </Field>
          <Field label="Project owner" hint="Defaults to the account manager.">
            <select key={team ? "team" : "loading"} name="owner" defaultValue="" className={inputClass}>
              <option value="">Same as the account manager</option>
              {team?.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Start">
              <input name="start" type="date" className={inputClass} />
            </Field>
            <Field label="Target completion">
              <input name="target" type="date" className={inputClass} />
            </Field>
          </div>
          <MilestoneRows rows={milestones} onChange={setMilestones} />
          <Checkbox name="kickoff" label="Add a kick-off task for the project owner" defaultChecked />
        </div>
      )}
      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={busy} icon={<UserCheck className="h-4 w-4" />}>
          Convert to client
        </Button>
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
