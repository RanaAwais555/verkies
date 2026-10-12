"use client";

import { AlertTriangle, FolderKanban, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { MilestoneRows, milestonesOf } from "@/components/clients/convert";
import { Badge, Button, controlClass, Empty, ErrorNote, Field, inputClass, Panel, Skeleton, Table, type Tone } from "@/components/ui";
import { api } from "@/lib/client";
import { formatDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Account360, Project, ProjectStatus, Service, TeamMember } from "@/lib/types";

export const PROJECT_STATUSES: { key: ProjectStatus; label: string; tone: Tone }[] = [
  { key: "not_started", label: "Not started", tone: "neutral" },
  { key: "planning", label: "Planning", tone: "blue" },
  { key: "active", label: "Active", tone: "accent" },
  { key: "at_risk", label: "At risk", tone: "red" },
  { key: "on_hold", label: "On hold", tone: "amber" },
  { key: "completed", label: "Completed", tone: "green" },
  { key: "cancelled", label: "Cancelled", tone: "neutral" },
];

export function ProjectStatusBadge({ status }: { status: ProjectStatus }) {
  const found = PROJECT_STATUSES.find((s) => s.key === status);
  return <Badge tone={found?.tone ?? "neutral"}>{found?.label ?? status}</Badge>;
}

/** The facts someone should look at: overdue milestones, high risks, overdue tasks, no owner. */
export function Attention({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) return null;
  return (
    <span className="inline-flex items-start gap-1 text-xs text-bad">
      <AlertTriangle aria-hidden className="mt-px h-3.5 w-3.5 shrink-0" />
      {reasons.join(" · ")}
    </span>
  );
}

function nextMilestone(p: Project) {
  return p.milestones.find((m) => !m.done) ?? null;
}

/** Projects as a table: who owns each, how far along it is, and what needs looking at. */
export function ProjectTable({ projects, showAccount = true }: { projects: Project[]; showAccount?: boolean }) {
  return (
    <Table testId="projects">
      <thead>
        <tr>
          <th>Project</th>
          <th>Status</th>
          <th>Owner</th>
          <th>Milestones</th>
          <th>Target</th>
        </tr>
      </thead>
      <tbody>
        {projects.map((p) => {
          const next = nextMilestone(p);
          return (
            <tr key={p.id} data-testid="project-row">
              <td className="min-w-[14rem]">
                <Link href={`/projects/${p.id}`} className="font-medium text-fg hover:text-accent-text hover:underline">
                  {p.name}
                </Link>
                <span className="block text-xs text-fg-3">
                  {showAccount && (
                    <>
                      <Link href={`/accounts/${p.account_id}`} className="hover:underline">
                        {p.account_name}
                      </Link>
                      {p.service_name && " · "}
                    </>
                  )}
                  {p.service_name}
                </span>
                <Attention reasons={p.requires_attention} />
              </td>
              <td>
                <ProjectStatusBadge status={p.status} />
              </td>
              <td className="whitespace-nowrap text-fg-2">{p.owner?.name ?? <span className="text-fg-3">Nobody</span>}</td>
              <td className="min-w-[10rem] text-fg-2">
                {p.milestones.length === 0 ? (
                  <span className="text-fg-3">None planned</span>
                ) : (
                  <>
                    <span className="tabular">
                      {p.milestones_done} of {p.milestones.length} done
                    </span>
                    {next && (
                      <span className="block text-xs text-fg-3">
                        Next: {next.name}
                        {next.due_date && `, ${formatDate(next.due_date)}`}
                      </span>
                    )}
                  </>
                )}
              </td>
              <td className="whitespace-nowrap tabular text-fg-2">
                {p.completed_on ? `Done ${formatDate(p.completed_on)}` : p.target_date ? formatDate(p.target_date) : <span className="text-fg-3">Not set</span>}
              </td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

/** A new project on an existing client: more work after the first one. */
export function NewProjectForm({ accountId, onCancel }: { accountId: string; onCancel: () => void }) {
  const router = useRouter();
  const { data: team } = useApi<TeamMember[]>("/team");
  const { data: services } = useApi<Service[]>("/catalogue/services");
  const { busy, error, run } = useAction();
  const [milestones, setMilestones] = useState<{ key: number; name: string; due: string }[]>([]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const created = await run(() =>
      api<Project>("/projects", {
        method: "POST",
        body: {
          account_id: accountId,
          name: String(data.get("name") ?? "").trim(),
          service_id: String(data.get("service") ?? "") || null,
          owner_id: String(data.get("owner") ?? "") || null,
          start_date: String(data.get("start") ?? "") || null,
          target_date: String(data.get("target") ?? "") || null,
          milestones: milestonesOf(milestones),
        },
      }),
    );
    if (created) router.push(`/projects/${created.id}`);
  }

  return (
    <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5" data-testid="new-project">
      <Field label="Project name">
        <input name="name" required maxLength={200} className={inputClass} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Service">
          <select key={services ? "services" : "loading"} name="service" defaultValue="" className={inputClass}>
            <option value="">Not set</option>
            {services?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Project owner">
          <select key={team ? "team" : "loading"} name="owner" defaultValue="" className={inputClass}>
            <option value="">Nobody yet</option>
            {team?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Start">
          <input name="start" type="date" className={inputClass} />
        </Field>
        <Field label="Target completion">
          <input name="target" type="date" className={inputClass} />
        </Field>
      </div>
      <MilestoneRows rows={milestones} onChange={setMilestones} />
      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={busy} icon={<Plus className="h-4 w-4" />}>
          Start project
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Who looks after a client day to day (§14). */
function AccountManager({ account }: { account: Account360 }) {
  const { data: team } = useApi<TeamMember[]>("/team");
  const { busy, error, run } = useAction();
  return (
    <div className="flex flex-wrap items-end gap-3">
      <Field label="Account manager">
        <select
          key={team ? "team" : "loading"}
          defaultValue={account.account_manager?.id ?? ""}
          disabled={busy}
          onChange={(e) => run(() => api(`/accounts/${account.id}/account-manager`, { method: "PUT", body: { account_manager_id: e.target.value || null } }))}
          className={controlClass}
        >
          <option value="">Not set</option>
          {team?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </Field>
      {account.client_since && <p className="pb-2 text-xs text-fg-3">Client since {formatDate(account.client_since)}</p>}
      <ErrorNote error={error} />
    </div>
  );
}

/** The Projects tab of an account. Projects start when a won deal is converted to a client. */
export function AccountProjects({ account }: { account: Account360 }) {
  const isClient = account.account_type === "customer";
  const { data, error } = useApi<Project[]>(`/projects?account_id=${account.id}&status=all`);
  const [adding, setAdding] = useState(false);
  return (
    <Panel
      title="Projects"
      description="Delivery after a deal is won: milestones, risks and tasks. Kept light; VROS is not a project tool."
      actions={
        isClient &&
        !adding && (
          <Button onClick={() => setAdding(true)} icon={<Plus className="h-4 w-4" />}>
            New project
          </Button>
        )
      }
    >
      <div className="space-y-4">
        {isClient && <AccountManager account={account} />}
        {adding && <NewProjectForm accountId={account.id} onCancel={() => setAdding(false)} />}
        {error ? (
          <ErrorNote error={error} />
        ) : !data ? (
          <Skeleton rows={3} />
        ) : data.length === 0 ? (
          <Empty icon={<FolderKanban className="h-4 w-4" />}>
            {isClient ? "No projects yet." : "No projects. A project starts when a won deal is converted to a client, from the deal on the Overview."}
          </Empty>
        ) : (
          <ProjectTable projects={data} showAccount={false} />
        )}
      </div>
    </Panel>
  );
}
