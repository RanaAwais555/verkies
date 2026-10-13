"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { EditTask, isOpen, TaskRow } from "@/components/crm/tasks";
import { Empty, ErrorNote, controlClass, PageHeader, Panel, Skeleton } from "@/components/ui";
import { SaveViewButton } from "@/components/views/save-view";
import { withQuery } from "@/lib/client";
import { isOverdue } from "@/lib/format";
import { useApi, useCanChange } from "@/lib/hooks";
import type { Task } from "@/lib/types";

/** The latest due time a "due" filter allows: the end of today, or now for overdue work. */
function dueBefore(due: string): string | undefined {
  if (due === "overdue") return new Date().toISOString();
  if (due === "today") {
    const end = new Date();
    end.setHours(23, 59, 59, 999);
    return end.toISOString();
  }
  return undefined;
}

export default function TasksPage() {
  // Filters live in the address, so a saved view such as "Follow-ups Today" can open this page.
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const whose = params.get("whose") === "all" ? "all" : "mine";
  const status = params.get("status") ?? "open";
  const due = ["today", "overdue"].includes(params.get("due") ?? "") ? params.get("due")! : "";
  const [editing, setEditing] = useState<string | null>(null);
  const writable = useCanChange();
  // Worked out once per choice of filter, so the request does not change on every render.
  const before = useMemo(() => dueBefore(due), [due]);
  const { data, error, mutate } = useApi<Task[]>(
    withQuery("/tasks", { mine: whose === "mine" ? "true" : "false", status, due_before: before, limit: 200 }),
  );
  const overdue = data?.filter((t) => isOpen(t) && isOverdue(t.due_at)).length ?? 0;

  function set(key: string, value: string, fallback: string) {
    const next = new URLSearchParams(params);
    if (value === fallback) next.delete(key);
    else next.set(key, value);
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Workspace"
        title="Tasks"
        description="Every next action across accounts, soonest first. Overdue work is marked in red."
        actions={<SaveViewButton suggestedName={due === "today" ? "Due by today" : due === "overdue" ? "Overdue tasks" : "Tasks"} />}
      />
      <Panel
        primary
        title={data ? `${data.length} ${data.length === 1 ? "task" : "tasks"}${overdue ? ` · ${overdue} overdue` : ""}` : "Loading"}
        actions={
          <div className="flex flex-wrap gap-2">
            <select value={due} onChange={(e) => set("due", e.target.value, "")} aria-label="Due" className={`${controlClass} w-40`}>
              <option value="">Any due date</option>
              <option value="today">Due by end of today</option>
              <option value="overdue">Overdue</option>
            </select>
            <select value={whose} onChange={(e) => set("whose", e.target.value, "mine")} aria-label="Whose tasks" className={`${controlClass} w-36`}>
              <option value="mine">Mine</option>
              <option value="all">Everyone&apos;s</option>
            </select>
            <select value={status} onChange={(e) => set("status", e.target.value, "open")} aria-label="Task status" className={`${controlClass} w-36`}>
              <option value="open">Open</option>
              <option value="in_progress">In progress</option>
              <option value="done">Done</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
        }
      >
        {error && <ErrorNote error={error} />}
        {!data && !error && <Skeleton rows={6} />}
        {data && data.length === 0 && <Empty>{status === "open" ? "No open tasks. Nothing is waiting on you." : "No tasks with this status."}</Empty>}
        {data && data.length > 0 && (
          <div role="list" className="divide-y divide-grid">
            {data.map((t) => (
              <div key={t.id}>
                <TaskRow task={t} showAccount onChange={() => mutate()} />
                {writable &&
                  isOpen(t) &&
                  (editing === t.id ? (
                    <EditTask
                      task={t}
                      onCancel={() => setEditing(null)}
                      onSaved={() => {
                        setEditing(null);
                        mutate();
                      }}
                    />
                  ) : (
                    <button type="button" className="mb-3 ml-5 text-xs text-fg-3 underline-offset-2 hover:text-fg hover:underline" onClick={() => setEditing(t.id)}>
                      Reassign or reschedule
                    </button>
                  ))}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
