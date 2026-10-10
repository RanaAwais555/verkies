"use client";

import { useState } from "react";

import { EditTask, isOpen, TaskRow } from "@/components/crm/tasks";
import { Empty, ErrorNote, controlClass, PageHeader, Panel, Skeleton } from "@/components/ui";
import { withQuery } from "@/lib/client";
import { isOverdue } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Task } from "@/lib/types";

export default function TasksPage() {
  const [whose, setWhose] = useState("mine");
  const [status, setStatus] = useState("open");
  const [editing, setEditing] = useState<string | null>(null);
  const { data, error, mutate } = useApi<Task[]>(withQuery("/tasks", { mine: whose === "mine" ? "true" : "false", status, limit: 200 }));
  const overdue = data?.filter((t) => isOpen(t) && isOverdue(t.due_at)).length ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Workspace" title="Tasks" description="Every next action across accounts, soonest first. Overdue work is marked in red." />
      <Panel
        primary
        title={data ? `${data.length} ${data.length === 1 ? "task" : "tasks"}${overdue ? ` · ${overdue} overdue` : ""}` : "Loading"}
        actions={
          <div className="flex flex-wrap gap-2">
            <select value={whose} onChange={(e) => setWhose(e.target.value)} aria-label="Whose tasks" className={`${controlClass} w-36`}>
              <option value="mine">Mine</option>
              <option value="all">Everyone&apos;s</option>
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Task status" className={`${controlClass} w-36`}>
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
                {isOpen(t) &&
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
