"use client";

import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { NewTaskForm, TaskRow } from "@/components/tasks";
import {
  Badge,
  BandBadge,
  Button,
  Card,
  Empty,
  ErrorNote,
  Field,
  formatDate,
  inputClass,
  label,
  Loading,
  Score,
  ScoreBar,
  SourceLink,
  StatusBadge,
  Tabs,
  TextLink,
} from "@/components/ui";
import { api } from "@/lib/client";
import { can, useApi, useSession } from "@/lib/hooks";
import type { Account360, AuditEntry, Task, TeamMember, TimelineEvent } from "@/lib/types";

function Overview({ account, refresh }: { account: Account360; refresh: () => void }) {
  const [settingFor, setSettingFor] = useState<string | null>(null);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Company">
        <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-muted">Website</dt>
          <dd>{account.website_url ? <SourceLink url={account.website_url} /> : "Unknown"}</dd>
          <dt className="text-muted">Domains</dt>
          <dd>{account.domains.join(", ") || "—"}</dd>
          <dt className="text-muted">Industry</dt>
          <dd>{account.industry ?? "Unknown"}</dd>
          <dt className="text-muted">Location</dt>
          <dd>{[account.hq_city, account.hq_country].filter(Boolean).join(", ") || "Unknown"}</dd>
          <dt className="text-muted">Size</dt>
          <dd>{account.company_size_band ? `${label(account.company_size_band)} (Companies House accounts)` : "Unknown"}</dd>
          <dt className="text-muted">Type</dt>
          <dd>{label(account.account_type)}</dd>
          <dt className="text-muted">Owner</dt>
          <dd>{account.owner?.name ?? "Unassigned"}</dd>
          <dt className="text-muted">Source</dt>
          <dd>{account.source ? label(account.source) : "—"}</dd>
        </dl>
        {account.description && <p className="mt-3 text-sm text-muted">{account.description}</p>}
        {account.latest_brief_run_id && (
          <p className="mt-3 text-sm"><TextLink href={`/research/${account.latest_brief_run_id}`}>Read the lead brief and evidence</TextLink></p>
        )}
      </Card>
      <Card title={<span className="flex items-center gap-2">Scores <BandBadge band={account.priority_band} /> <Score value={account.priority_score} /></span>}>
        <div className="space-y-1.5">
          {Object.entries(account.scores).map(([k, v]) => <ScoreBar key={k} name={k} value={v} />)}
        </div>
      </Card>
      <Card title="Opportunities">
        {account.opportunities.length === 0 ? <Empty>No opportunity detected.</Empty> : (
          <ul className="space-y-3" data-testid="opportunities">
            {account.opportunities.map((o) => (
              <li key={o.id} className="space-y-1 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{o.name}</span>
                  {o.service_name && <Badge tone="blue">{o.service_name}</Badge>}
                  {o.requires_attention.length > 0 && <Badge tone="red">Requires attention</Badge>}
                </div>
                <p className="text-muted">{o.problem}</p>
                {o.requires_attention.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs text-red-600">{o.requires_attention.join("; ")}</p>
                    {settingFor === o.id ? (
                      <NewTaskForm
                        accountId={account.id}
                        opportunityId={o.id}
                        submitLabel="Set next action"
                        onCreated={() => { setSettingFor(null); refresh(); }}
                      />
                    ) : (
                      <Button variant="secondary" onClick={() => setSettingFor(o.id)}>Set next action</Button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Contacts">
        {account.contacts.length === 0 ? <Empty>No people named on the company&apos;s pages.</Empty> : (
          <ul className="space-y-2 text-sm" data-testid="contacts">
            {account.contacts.map((c) => (
              <li key={c.id}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{c.name}</span>
                  {c.title && <span className="text-muted">{c.title}</span>}
                  {c.decision_maker_role && <Badge>{label(c.decision_maker_role)}</Badge>}
                  <Badge tone={c.verification_status === "verified" ? "green" : "neutral"}>{label(c.verification_status)}</Badge>
                </div>
                <div className="text-xs text-muted">
                  {c.email ?? "Email unknown"} · {c.phone ?? "phone unknown"} · {c.source_url && <SourceLink url={c.source_url} />}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Leads({ account }: { account: Account360 }) {
  return (
    <Card title="Leads">
      <ul className="divide-y divide-border text-sm">
        {account.leads.map((l) => (
          <li key={l.id} className="flex flex-wrap items-center gap-2 py-2">
            <StatusBadge status={l.status} />
            <BandBadge band={l.priority_band} />
            <Score value={l.priority_score} />
            <span className="text-muted">{label(l.source)} · qualified {formatDate(l.qualified_at)} · owner {l.owner?.name ?? "—"}</span>
            {l.research_run_id && <TextLink href={`/research/${l.research_run_id}`}>Research</TextLink>}
          </li>
        ))}
      </ul>
      <h3 className="mb-1 mt-4 text-sm font-semibold">Research runs</h3>
      <ul className="space-y-1 text-sm">
        {account.research_runs.map((r) => (
          <li key={r.id} className="flex items-center gap-2">
            <TextLink href={`/research/${r.id}`}>{r.normalised_domain}</TextLink>
            <StatusBadge status={r.review_status} />
            <span className="text-xs text-muted">{formatDate(r.created_at, true)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function EditTask({ task, onSaved }: { task: Task; onSaved: () => void }) {
  const { data: team } = useApi<TeamMember[]>("/team");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const due = String(data.get("due") ?? "");
    setBusy(true);
    setError(null);
    try {
      await api(`/tasks/${task.id}`, {
        method: "PATCH",
        body: { owner_id: data.get("owner") || null, due_at: due ? new Date(`${due}T17:00:00`).toISOString() : null },
      });
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="flex flex-wrap items-end gap-2 pb-2">
      <Field label="Owner">
        <select key={team ? "team" : "loading"} name="owner" defaultValue={task.owner_id ?? ""} className={inputClass}>
          <option value="">Nobody</option>
          {team?.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
      </Field>
      <Field label="Due">
        <input name="due" type="date" defaultValue={task.due_at ? task.due_at.slice(0, 10) : ""} className={inputClass} />
      </Field>
      <Button type="submit" variant="secondary" busy={busy}>Save</Button>
      <ErrorNote error={error} />
    </form>
  );
}

function Tasks({ account, refresh }: { account: Account360; refresh: () => void }) {
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  return (
    <Card title="Tasks" actions={<Button variant="secondary" onClick={() => setAdding(!adding)}>{adding ? "Close" : "Add task"}</Button>}>
      {adding && <div className="mb-3"><NewTaskForm accountId={account.id} onCreated={() => { setAdding(false); refresh(); }} /></div>}
      {account.tasks.length === 0 && <Empty>No tasks.</Empty>}
      <div role="list" className="divide-y divide-border">
        {account.tasks.map((t) => (
          <div key={t.id}>
            <TaskRow task={t} onChange={refresh} />
            {(t.status === "open" || t.status === "in_progress") && (
              editing === t.id
                ? <EditTask task={t} onSaved={() => { setEditing(null); refresh(); }} />
                : <button className="mb-2 text-xs text-muted underline" onClick={() => setEditing(t.id)}>Reassign or reschedule</button>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function Timeline({ id }: { id: string }) {
  const { data, error } = useApi<TimelineEvent[]>(`/accounts/${id}/timeline?limit=500`);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  return (
    <Card title="Timeline">
      <ol className="space-y-2" data-testid="timeline">
        {data.map((e) => (
          <li key={e.id} className="grid grid-cols-[9rem_1fr] gap-3 text-sm">
            <time className="text-xs text-muted" dateTime={e.occurred_at}>{formatDate(e.occurred_at, true)}</time>
            <span>
              {e.summary}
              <span className="text-xs text-muted"> · {e.actor?.name ?? "system"}</span>
            </span>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function Audit({ id }: { id: string }) {
  const { data, error } = useApi<AuditEntry[]>(`/accounts/${id}/audit?limit=500`);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  return (
    <Card title="Audit log">
      <ul className="space-y-2 text-sm" data-testid="audit">
        {data.map((e) => (
          <li key={e.id}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs">{e.action}</span>
              <span className="text-xs text-muted">{formatDate(e.occurred_at, true)} · {e.source}</span>
            </div>
            {e.reason && <p className="text-xs">Reason: {e.reason}</p>}
            {e.new_value && <pre className="mt-1 overflow-x-auto rounded bg-surface p-2 text-xs">{JSON.stringify(e.new_value, null, 2)}</pre>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function AccountPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session } = useSession();
  const { data: account, error, mutate } = useApi<Account360>(`/accounts/${id}`);
  const [tab, setTab] = useState("overview");
  if (error) return <ErrorNote error={error} />;
  if (!account) return <Loading />;
  const tabs = [
    { key: "overview", label: "Overview" },
    { key: "leads", label: `Leads (${account.leads.length})` },
    { key: "tasks", label: `Tasks (${account.open_tasks} open)` },
    { key: "timeline", label: "Timeline" },
    ...(can(session, "audit.read") ? [{ key: "audit", label: "Audit" }] : []),
  ];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{account.name}</h1>
        <Badge>{label(account.account_type)}</Badge>
        <span className="text-sm text-muted">{account.primary_domain}</span>
      </div>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" && <Overview account={account} refresh={() => mutate()} />}
      {tab === "leads" && <Leads account={account} />}
      {tab === "tasks" && <Tasks account={account} refresh={() => mutate()} />}
      {tab === "timeline" && <Timeline id={id} />}
      {tab === "audit" && <Audit id={id} />}
    </div>
  );
}
