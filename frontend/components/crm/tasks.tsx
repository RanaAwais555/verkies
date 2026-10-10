"use client";

import { Check, Plus } from "lucide-react";
import type { FormEvent } from "react";

import { Badge, Button, ErrorNote, Field, inputClass, StatusBadge, TextLink } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { endOfWorkingDay, formatDate, initials, isOverdue, relativeDate } from "@/lib/format";
import { useAction, useApi, useSession } from "@/lib/hooks";
import type { Task, TeamMember } from "@/lib/types";

const PRIORITY_TONE = { urgent: "red", high: "amber", low: "neutral", normal: "neutral" } as const;

export function isOpen(task: Task): boolean {
  return task.status === "open" || task.status === "in_progress";
}

/** One task: what, when, who, and a one-click way to complete it. */
export function TaskRow({ task, showAccount, onChange }: { task: Task; showAccount?: boolean; onChange?: () => void }) {
  const { busy, error, run } = useAction();
  const open = isOpen(task);
  const overdue = open && isOverdue(task.due_at);

  async function complete() {
    if (await run(() => api(`/tasks/${task.id}/complete`, { method: "POST", body: {} }).then(() => true))) onChange?.();
  }

  return (
    <div role="listitem" className="flex items-start gap-3 py-3 first:pt-0 last:pb-0" data-testid="task">
      <span
        aria-hidden
        className={cx("mt-1.5 h-2 w-2 shrink-0 rounded-full", !open ? "bg-ok" : overdue ? "bg-bad" : task.due_at && relativeDate(task.due_at) === "Today" ? "bg-warn" : "bg-accent")}
      />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={open ? "font-medium text-fg" : "text-fg-3 line-through"}>{task.title}</span>
          {task.priority !== "normal" && <Badge tone={PRIORITY_TONE[task.priority]}>{task.priority}</Badge>}
          {!open && <StatusBadge status={task.status} />}
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-3">
          {showAccount && task.account_name && <TextLink href={`/accounts/${task.account_id}`}>{task.account_name}</TextLink>}
          <span className={overdue ? "font-medium text-bad" : undefined} title={formatDate(task.due_at, true)}>
            {task.due_at ? `Due ${formatDate(task.due_at)}` : "No due date"}
            {overdue ? " (overdue)" : ""}
          </span>
          <span className="inline-flex items-center gap-1.5">
            {task.owner_name && (
              <span aria-hidden className="grid h-4 w-4 place-items-center rounded-full bg-accent-soft text-[8px] font-semibold text-accent-text">
                {initials(task.owner_name)}
              </span>
            )}
            Owner: {task.owner_name ?? "nobody"}
          </span>
        </div>
        <ErrorNote error={error} />
      </div>
      {open && (
        <Button busy={busy} onClick={complete} icon={<Check className="h-3.5 w-3.5" />} className="h-8 shrink-0 px-2.5 text-xs">
          Mark done
        </Button>
      )}
    </div>
  );
}

/** A new task on an account. With an opportunity it becomes that opportunity's next action. */
export function NewTaskForm({
  accountId,
  opportunityId,
  submitLabel = "Add task",
  onCreated,
  onCancel,
}: {
  accountId: string;
  opportunityId?: string;
  submitLabel?: string;
  onCreated: () => void;
  onCancel?: () => void;
}) {
  const { data: session } = useSession();
  const { data: team } = useApi<TeamMember[]>("/team");
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const created = await run(() =>
      api("/tasks", {
        method: "POST",
        body: {
          account_id: accountId,
          opportunity_id: opportunityId ?? null,
          title: String(data.get("title") ?? "").trim(),
          owner_id: data.get("owner") || null,
          due_at: endOfWorkingDay(String(data.get("due") ?? "")),
        },
      }).then(() => true),
    );
    if (created) {
      form.reset();
      onCreated();
    }
  }

  return (
    <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5" data-testid="new-task">
      <Field label="What needs doing">
        <input name="title" required maxLength={200} className={inputClass} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Owner">
          {/* Re-mounted when the team arrives, so the default owner applies to real options. */}
          <select key={team ? "team" : "loading"} name="owner" defaultValue={session?.user.id ?? ""} className={inputClass}>
            <option value="">Nobody</option>
            {team?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Due">
          <input name="due" type="date" required={!!opportunityId} className={inputClass} />
        </Field>
      </div>
      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={busy} icon={<Plus className="h-4 w-4" />}>
          {submitLabel}
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

/** Reassign an open task or move its due date. */
export function EditTask({ task, onSaved, onCancel }: { task: Task; onSaved: () => void; onCancel: () => void }) {
  const { data: team } = useApi<TeamMember[]>("/team");
  const { busy, error, run } = useAction();

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const saved = await run(() =>
      api(`/tasks/${task.id}`, {
        method: "PATCH",
        body: { owner_id: data.get("owner") || null, due_at: endOfWorkingDay(String(data.get("due") ?? "")) },
      }).then(() => true),
    );
    if (saved) onSaved();
  }

  return (
    <form onSubmit={save} className="animate-rise mb-3 flex flex-wrap items-end gap-3 rounded-xl border border-border bg-surface-2 p-3">
      <Field label="Owner">
        <select key={team ? "team" : "loading"} name="owner" defaultValue={task.owner_id ?? ""} className={inputClass}>
          <option value="">Nobody</option>
          {team?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Due">
        <input name="due" type="date" defaultValue={task.due_at ? task.due_at.slice(0, 10) : ""} className={inputClass} />
      </Field>
      <Button type="submit" busy={busy}>
        Save
      </Button>
      <Button variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
      <div className="basis-full">
        <ErrorNote error={error} />
      </div>
    </form>
  );
}
