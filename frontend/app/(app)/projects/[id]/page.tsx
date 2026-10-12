"use client";

import { Check, Flag, Plus, Save, ShieldAlert, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Attention, PROJECT_STATUSES, ProjectStatusBadge } from "@/components/clients/projects";
import { NewTaskForm, TaskRow } from "@/components/crm/tasks";
import { DocumentsPanel } from "@/components/documents/documents";
import { Badge, Button, Empty, ErrorNote, Field, IconButton, inputClass, PageHeader, Panel, Skeleton, type Tone } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { formatDate, money } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Milestone, ProjectDetail, ProjectRisk, Service, TeamMember } from "@/lib/types";

const SEVERITY_TONE: Record<ProjectRisk["severity"], Tone> = { low: "neutral", medium: "amber", high: "red" };

function MilestoneItem({ milestone, onChange }: { milestone: Milestone; onChange: () => void }) {
  const { busy, error, run } = useAction();
  const toggle = () => run(() => api(`/milestones/${milestone.id}`, { method: "PATCH", body: { done: !milestone.done } }).then(onChange));
  const remove = () => run(() => api(`/milestones/${milestone.id}`, { method: "DELETE" }).then(onChange));
  return (
    <li className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0" data-testid="milestone">
      <button
        type="button"
        role="checkbox"
        aria-checked={milestone.done}
        aria-label={`${milestone.done ? "Reopen" : "Mark reached"}: ${milestone.name}`}
        disabled={busy}
        onClick={toggle}
        className={cx(
          "mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-md border transition-colors",
          milestone.done ? "border-ok bg-ok text-white" : "border-border-strong bg-surface hover:border-accent",
        )}
      >
        {milestone.done && <Check aria-hidden className="h-3 w-3" strokeWidth={3} />}
      </button>
      <span className="min-w-0 flex-1">
        <span className={cx("block text-[13px]", milestone.done ? "text-fg-3 line-through" : "font-medium text-fg")}>{milestone.name}</span>
        <span className={cx("text-xs", milestone.overdue ? "text-bad" : "text-fg-3")}>
          {milestone.done && milestone.completed_at
            ? `Reached ${formatDate(milestone.completed_at)}`
            : milestone.due_date
              ? `${milestone.overdue ? "Overdue: was due" : "Due"} ${formatDate(milestone.due_date)}`
              : "No date"}
        </span>
        <ErrorNote error={error} />
      </span>
      <IconButton label={`Delete milestone ${milestone.name}`} onClick={remove}>
        <Trash2 className="h-4 w-4" />
      </IconButton>
    </li>
  );
}

function Milestones({ project, refresh }: { project: ProjectDetail; refresh: () => void }) {
  const { busy, error, run } = useAction();

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const added = await run(() =>
      api(`/projects/${project.id}/milestones`, {
        method: "POST",
        body: { name: String(data.get("name") ?? "").trim(), due_date: String(data.get("due") ?? "") || null },
      }).then(() => true),
    );
    if (added) {
      form.reset();
      refresh();
    }
  }

  return (
    <Panel title="Milestones" description={`${project.milestones_done} of ${project.milestones.length} reached.`} testId="milestones">
      <div className="space-y-4">
        {project.milestones.length === 0 ? (
          <Empty icon={<Flag className="h-4 w-4" />}>No milestones planned.</Empty>
        ) : (
          <ul className="divide-y divide-grid">
            {project.milestones.map((m) => (
              <MilestoneItem key={m.id} milestone={m} onChange={refresh} />
            ))}
          </ul>
        )}
        <form onSubmit={add} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_10rem_auto] sm:items-end">
          <Field label="New milestone">
            <input name="name" required maxLength={200} className={inputClass} />
          </Field>
          <Field label="Due">
            <input name="due" type="date" className={inputClass} />
          </Field>
          <Button type="submit" busy={busy} icon={<Plus className="h-4 w-4" />}>
            Add
          </Button>
        </form>
        <ErrorNote error={error} />
      </div>
    </Panel>
  );
}

function RiskItem({ risk, onChange }: { risk: ProjectRisk; onChange: () => void }) {
  const { busy, error, run } = useAction();
  const [resolving, setResolving] = useState(false);

  async function resolve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const done = await run(() =>
      api(`/risks/${risk.id}`, { method: "PATCH", body: { resolved: true, resolution: String(data.get("resolution") ?? "").trim() || null } }).then(() => true),
    );
    if (done) onChange();
  }

  return (
    <li className="space-y-2 py-3 first:pt-0 last:pb-0" data-testid="risk">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className={cx("min-w-0 flex-1 text-[13px]", risk.resolved ? "text-fg-3" : "text-fg")}>{risk.description}</p>
        <Badge tone={risk.resolved ? "neutral" : SEVERITY_TONE[risk.severity]}>{risk.resolved ? "Resolved" : `${risk.severity} risk`}</Badge>
      </div>
      <p className="text-xs text-fg-3">
        Raised {formatDate(risk.created_at)}
        {risk.resolved_at && ` · resolved ${formatDate(risk.resolved_at)}`}
        {risk.resolution && `: ${risk.resolution}`}
      </p>
      {!risk.resolved &&
        (resolving ? (
          <form onSubmit={resolve} className="flex flex-wrap items-end gap-2">
            <Field label="How it was resolved (optional)" className="min-w-0 flex-1">
              <input name="resolution" maxLength={2000} className={inputClass} />
            </Field>
            <Button type="submit" variant="primary" busy={busy}>
              Resolve
            </Button>
            <Button variant="ghost" onClick={() => setResolving(false)}>
              Cancel
            </Button>
          </form>
        ) : (
          <Button className="h-7 px-2.5 text-xs" onClick={() => setResolving(true)}>
            Mark resolved
          </Button>
        ))}
      <ErrorNote error={error} />
    </li>
  );
}

function Risks({ project, refresh }: { project: ProjectDetail; refresh: () => void }) {
  const { busy, error, run } = useAction();
  const [raising, setRaising] = useState(false);

  async function raise(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const raised = await run(() =>
      api(`/projects/${project.id}/risks`, {
        method: "POST",
        body: { description: String(data.get("description") ?? "").trim(), severity: data.get("severity") },
      }).then(() => true),
    );
    if (raised) {
      setRaising(false);
      refresh();
    }
  }

  return (
    <Panel
      title="Risks"
      description="Anything that could hurt delivery. Open until someone resolves it."
      testId="risks"
      actions={
        !raising && (
          <Button onClick={() => setRaising(true)} icon={<ShieldAlert className="h-4 w-4" />}>
            Raise a risk
          </Button>
        )
      }
    >
      <div className="space-y-4">
        {raising && (
          <form onSubmit={raise} className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5">
            <Field label="What could go wrong">
              <textarea name="description" required maxLength={4000} rows={2} className={cx(inputClass, "resize-y")} />
            </Field>
            <Field label="Severity">
              <select name="severity" defaultValue="medium" className={inputClass}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </Field>
            <ErrorNote error={error} />
            <div className="flex flex-wrap gap-2">
              <Button type="submit" variant="primary" busy={busy}>
                Raise risk
              </Button>
              <Button variant="ghost" onClick={() => setRaising(false)}>
                Cancel
              </Button>
            </div>
          </form>
        )}
        {project.risks.length === 0 ? (
          <Empty icon={<ShieldAlert className="h-4 w-4" />}>No risks raised.</Empty>
        ) : (
          <ul className="divide-y divide-grid">
            {project.risks.map((r) => (
              <RiskItem key={r.id} risk={r} onChange={refresh} />
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}

function Tasks({ project, refresh }: { project: ProjectDetail; refresh: () => void }) {
  const [adding, setAdding] = useState(false);
  return (
    <Panel
      title="Tasks"
      description={`${project.open_tasks} open${project.overdue_tasks ? `, ${project.overdue_tasks} overdue` : ""}.`}
      testId="project-tasks"
      actions={
        !adding && (
          <Button onClick={() => setAdding(true)} icon={<Plus className="h-4 w-4" />}>
            Add task
          </Button>
        )
      }
    >
      <div className="space-y-4">
        {adding && (
          <NewTaskForm
            accountId={project.account_id}
            projectId={project.id}
            onCancel={() => setAdding(false)}
            onCreated={() => {
              setAdding(false);
              refresh();
            }}
          />
        )}
        {project.tasks.length === 0 ? (
          <Empty>No tasks on this project.</Empty>
        ) : (
          <div role="list" className="divide-y divide-grid">
            {project.tasks.map((t) => (
              <TaskRow key={t.id} task={t} onChange={refresh} />
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

function Details({ project, refresh }: { project: ProjectDetail; refresh: () => void }) {
  const { data: team } = useApi<TeamMember[]>("/team");
  const { data: services } = useApi<Service[]>("/catalogue/services");
  const { busy, error, run } = useAction();
  const [saved, setSaved] = useState(false);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(false);
    const data = new FormData(event.currentTarget);
    const done = await run(() =>
      api(`/projects/${project.id}`, {
        method: "PATCH",
        body: {
          name: String(data.get("name") ?? "").trim() || project.name,
          status: data.get("status"),
          owner_id: String(data.get("owner") ?? "") || null,
          service_id: String(data.get("service") ?? "") || null,
          start_date: String(data.get("start") ?? "") || null,
          target_date: String(data.get("target") ?? "") || null,
          notes: String(data.get("notes") ?? ""),
        },
      }).then(() => true),
    );
    if (done) {
      setSaved(true);
      refresh();
    }
  }

  return (
    <Panel title="Details" testId="project-details">
      <form key={project.status + project.target_date + project.owner?.id} onSubmit={save} className="space-y-3">
        <Field label="Name">
          <input name="name" defaultValue={project.name} required maxLength={200} className={inputClass} />
        </Field>
        <Field label="Status">
          <select name="status" defaultValue={project.status} className={inputClass}>
            {PROJECT_STATUSES.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Project owner">
          <select key={team ? "team" : "loading"} name="owner" defaultValue={project.owner?.id ?? ""} className={inputClass}>
            <option value="">Nobody</option>
            {team?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Service">
          <select key={services ? "services" : "loading"} name="service" defaultValue={project.service_id ?? ""} className={inputClass}>
            <option value="">Not set</option>
            {services?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Start">
            <input name="start" type="date" defaultValue={project.start_date ?? ""} className={inputClass} />
          </Field>
          <Field label="Target">
            <input name="target" type="date" defaultValue={project.target_date ?? ""} className={inputClass} />
          </Field>
        </div>
        <Field label="Notes">
          <textarea name="notes" defaultValue={project.notes ?? ""} maxLength={10000} rows={4} className={cx(inputClass, "resize-y")} />
        </Field>
        <ErrorNote error={error} />
        <div className="flex items-center gap-3">
          <Button type="submit" variant="primary" busy={busy} icon={<Save className="h-4 w-4" />}>
            Save
          </Button>
          {saved && <span className="text-xs text-ok">Saved.</span>}
        </div>
      </form>
    </Panel>
  );
}

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const { data: project, error, mutate } = useApi<ProjectDetail>(`/projects/${id}`);
  if (error) return <ErrorNote error={error} />;
  if (!project) return <Skeleton rows={8} />;
  const refresh = () => void mutate();

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Project"
        title={project.name}
        badges={<ProjectStatusBadge status={project.status} />}
        description={
          <span className="space-y-1">
            <span className="block">
              <Link href={`/accounts/${project.account_id}`} className="font-medium text-accent-text hover:underline">
                {project.account_name}
              </Link>
              {project.service_name && ` · ${project.service_name}`}
              {` · owner: ${project.owner?.name ?? "nobody"}`}
              {project.completed_on
                ? ` · completed ${formatDate(project.completed_on)}`
                : project.target_date && ` · target ${formatDate(project.target_date)}`}
            </span>
            {project.deal && (
              <span className="block text-fg-3">
                From the deal {project.deal.name} ({money(project.deal.value, project.deal.currency)}
                {project.deal.closed_at && `, won ${formatDate(project.deal.closed_at)}`})
              </span>
            )}
            <Attention reasons={project.requires_attention} />
          </span>
        }
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
        <div className="flex min-w-0 flex-col gap-4">
          <Milestones project={project} refresh={refresh} />
          <Tasks project={project} refresh={refresh} />
          <Risks project={project} refresh={refresh} />
          <DocumentsPanel
            accountId={project.account_id}
            projectId={project.id}
            description="Files for this project: requirements, designs, notes and sign-offs."
          />
        </div>
        <aside className="min-w-0" aria-label="Project details">
          <Details project={project} refresh={refresh} />
        </aside>
      </div>
    </div>
  );
}
