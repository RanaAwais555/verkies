"use client";

import { useState, type FormEvent } from "react";

import { Badge, Button, ErrorNote, Field, formatDate, inputClass, isOverdue, StatusBadge, TextLink } from "@/components/ui";
import { api } from "@/lib/client";
import { useApi, useSession } from "@/lib/hooks";
import type { Task, TeamMember } from "@/lib/types";

export function TaskRow({ task, showAccount, onChange }: { task: Task; showAccount?: boolean; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const open = task.status === "open" || task.status === "in_progress";

  async function complete() {
    setBusy(true);
    setError(null);
    try {
      await api(`/tasks/${task.id}/complete`, { method: "POST", body: {} });
      onChange();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div role="listitem" className="space-y-1 py-2" data-testid="task">
      <div className="flex flex-wrap items-center gap-2">
        <span className={open ? "font-medium" : "text-muted line-through"}>{task.title}</span>
        {task.priority !== "normal" && <Badge tone={task.priority === "urgent" ? "red" : "amber"}>{task.priority}</Badge>}
        {!open && <StatusBadge status={task.status} />}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        {showAccount && task.account_name && <TextLink href={`/accounts/${task.account_id}`}>{task.account_name}</TextLink>}
        <span className={open && isOverdue(task.due_at) ? "font-medium text-red-600" : undefined}>
          Due {formatDate(task.due_at)}{open && isOverdue(task.due_at) ? " (overdue)" : ""}
        </span>
        <span>Owner: {task.owner_name ?? "nobody"}</span>
        {open && (
          <Button variant="secondary" className="py-0.5 text-xs" busy={busy} onClick={complete}>
            Mark done
          </Button>
        )}
      </div>
      <ErrorNote error={error} />
    </div>
  );
}

/** A new task on an account; with an opportunity it becomes that opportunity's next action. */
export function NewTaskForm({
  accountId,
  opportunityId,
  submitLabel = "Add task",
  onCreated,
}: {
  accountId: string;
  opportunityId?: string;
  submitLabel?: string;
  onCreated: () => void;
}) {
  const { data: session } = useSession();
  const { data: team } = useApi<TeamMember[]>("/team");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const due = String(data.get("due") ?? "");
    setBusy(true);
    setError(null);
    try {
      await api("/tasks", {
        method: "POST",
        body: {
          account_id: accountId,
          opportunity_id: opportunityId ?? null,
          title: String(data.get("title") ?? "").trim(),
          owner_id: data.get("owner") || null,
          due_at: due ? new Date(`${due}T17:00:00`).toISOString() : null,
        },
      });
      form.reset();
      onCreated();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2 rounded-md border border-border p-3" data-testid="new-task">
      <Field label="What needs doing">
        <input name="title" required maxLength={200} className={inputClass} />
      </Field>
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Owner">
          {/* Re-mounted when the team arrives, so the default owner applies to real options. */}
          <select key={team ? "team" : "loading"} name="owner" defaultValue={session?.user.id ?? ""} className={inputClass}>
            <option value="">Nobody</option>
            {team?.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </Field>
        <Field label="Due">
          <input name="due" type="date" required={!!opportunityId} className={inputClass} />
        </Field>
      </div>
      <ErrorNote error={error} />
      <Button type="submit" busy={busy}>{submitLabel}</Button>
    </form>
  );
}
