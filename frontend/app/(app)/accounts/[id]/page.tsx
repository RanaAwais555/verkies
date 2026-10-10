"use client";

import { AlertTriangle, ArrowRight, Globe, Plus, UserRound } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";

import { EditTask, isOpen, NewTaskForm, TaskRow } from "@/components/crm/tasks";
import { Timeline } from "@/components/crm/timeline";
import {
  Badge,
  BandBadge,
  Button,
  Empty,
  ErrorNote,
  LinkButton,
  PageHeader,
  Panel,
  ScoreBar,
  ScoreChip,
  Skeleton,
  SourceLink,
  StatusBadge,
  Tabs,
  TextLink,
} from "@/components/ui";
import { formatDate, initials, label, percent } from "@/lib/format";
import { can, useApi, useSession, useTab } from "@/lib/hooks";
import type { Account360, AuditEntry } from "@/lib/types";

function Facts({ account }: { account: Account360 }) {
  const rows: [string, React.ReactNode][] = [
    ["Website", account.website_url ? <SourceLink url={account.website_url} /> : "Unknown"],
    ["Domains", account.domains.join(", ") || "—"],
    ["Industry", account.industry ?? "Unknown"],
    ["Location", [account.hq_city, account.hq_country].filter(Boolean).join(", ") || "Unknown"],
    ["Size", account.company_size_band ? `${label(account.company_size_band)} (Companies House accounts)` : "Unknown"],
    ["Legal name", account.legal_name ?? "Unknown"],
    ["Source", account.source ? label(account.source) : "—"],
  ];
  return (
    <dl className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-2.5 text-[13px]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-fg-3">{k}</dt>
          <dd className="min-w-0 text-fg">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Overview({ account, refresh }: { account: Account360; refresh: () => void }) {
  const [settingFor, setSettingFor] = useState<string | null>(null);
  return (
    <div className="flex flex-wrap items-start gap-5">
      <div className="flex min-w-0 flex-[2_1_480px] flex-col gap-5">
        <Panel title="Opportunities" primary>
          {account.opportunities.length === 0 ? (
            <Empty>No opportunity detected.</Empty>
          ) : (
            <ul className="divide-y divide-grid" data-testid="opportunities">
              {account.opportunities.map((o) => (
                <li key={o.id} className="space-y-2 py-3 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-fg">{o.name}</span>
                    {o.service_name && <Badge tone="blue">{o.service_name}</Badge>}
                    <Badge>{label(o.stage)}</Badge>
                    {o.requires_attention.length > 0 && <Badge tone="red">Requires attention</Badge>}
                  </div>
                  <p className="text-[13px] leading-relaxed text-fg-2">{o.problem}</p>
                  {o.requires_attention.length > 0 && (
                    <div className="space-y-2.5">
                      <p className="flex items-center gap-1.5 text-xs text-bad">
                        <AlertTriangle aria-hidden className="h-3.5 w-3.5" />
                        {o.requires_attention.join("; ")}
                      </p>
                      {settingFor === o.id ? (
                        <NewTaskForm
                          accountId={account.id}
                          opportunityId={o.id}
                          submitLabel="Set next action"
                          onCancel={() => setSettingFor(null)}
                          onCreated={() => {
                            setSettingFor(null);
                            refresh();
                          }}
                        />
                      ) : (
                        <Button onClick={() => setSettingFor(o.id)} icon={<Plus className="h-4 w-4" />}>
                          Set next action
                        </Button>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Contacts" collapsible>
          {account.contacts.length === 0 ? (
            <Empty icon={<UserRound className="h-4 w-4" />}>No people named on the company&apos;s pages.</Empty>
          ) : (
            <ul className="divide-y divide-grid" data-testid="contacts">
              {account.contacts.map((c) => (
                <li key={c.id} className="flex gap-3 py-3 first:pt-0 last:pb-0">
                  <span aria-hidden className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-info-soft text-[11px] font-semibold text-info">
                    {initials(c.name)}
                  </span>
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-fg">{c.name}</span>
                      {c.title && <span className="text-[13px] text-fg-2">{c.title}</span>}
                      {c.decision_maker_role ? <Badge tone="accent">{label(c.decision_maker_role)}</Badge> : <Badge tone="amber">Role unconfirmed</Badge>}
                      <Badge tone={c.verification_status === "verified" ? "green" : "neutral"}>{label(c.verification_status)}</Badge>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-2 text-xs text-fg-3">
                      <span>{c.email ?? "Email unknown"}</span>
                      <span>· {c.phone ?? "phone unknown"}</span>
                      <span>· confidence {percent(c.confidence)}</span>
                      {c.source_url && <SourceLink url={c.source_url} />}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <aside className="flex min-w-0 flex-[1_1_300px] flex-col gap-5 lg:sticky lg:top-20 lg:max-w-[400px]" aria-label="Account context">
        <Panel title="Company">
          <Facts account={account} />
          {account.description && <p className="mt-3 text-[13px] leading-relaxed text-fg-2">{account.description}</p>}
          {account.latest_brief_run_id && (
            <LinkButton href={`/research/${account.latest_brief_run_id}`} variant="ghost" icon={<ArrowRight className="h-4 w-4" />} className="mt-3 -ml-3">
              Read the lead brief and evidence
            </LinkButton>
          )}
        </Panel>
        <Panel
          title="Scores"
          collapsible
          actions={
            <span className="flex items-center gap-2">
              <ScoreChip value={account.priority_score} />
              <BandBadge band={account.priority_band} />
            </span>
          }
        >
          <div className="space-y-2">
            {Object.entries(account.scores).map(([k, v]) => (
              <ScoreBar key={k} name={k} value={v} />
            ))}
          </div>
        </Panel>
      </aside>
    </div>
  );
}

function Leads({ account }: { account: Account360 }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel title="Leads">
        {account.leads.length === 0 ? (
          <Empty>No lead on this account.</Empty>
        ) : (
          <ul className="divide-y divide-grid">
            {account.leads.map((l) => (
              <li key={l.id} className="flex flex-wrap items-center gap-2 py-2.5 text-[13px] first:pt-0 last:pb-0">
                <ScoreChip value={l.priority_score} />
                <StatusBadge status={l.status} />
                <BandBadge band={l.priority_band} />
                <span className="text-fg-3">
                  {label(l.source)} · qualified {formatDate(l.qualified_at)} · owner {l.owner?.name ?? "—"}
                </span>
                {l.research_run_id && <TextLink href={`/research/${l.research_run_id}`}>Brief</TextLink>}
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Panel title="Research runs">
        {account.research_runs.length === 0 ? (
          <Empty>Never researched.</Empty>
        ) : (
          <ul className="divide-y divide-grid">
            {account.research_runs.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2 py-2.5 text-[13px] first:pt-0 last:pb-0">
                <TextLink href={`/research/${r.id}`}>{r.normalised_domain}</TextLink>
                <StatusBadge status={r.review_status} />
                <span className="text-xs text-fg-3">{formatDate(r.created_at, true)}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function Tasks({ account, refresh }: { account: Account360; refresh: () => void }) {
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  return (
    <Panel
      title="Tasks"
      primary
      actions={
        !adding && (
          <Button onClick={() => setAdding(true)} icon={<Plus className="h-4 w-4" />}>
            Add task
          </Button>
        )
      }
    >
      {adding && (
        <div className="mb-4">
          <NewTaskForm
            accountId={account.id}
            onCancel={() => setAdding(false)}
            onCreated={() => {
              setAdding(false);
              refresh();
            }}
          />
        </div>
      )}
      {account.tasks.length === 0 && !adding && <Empty>No tasks on this account.</Empty>}
      <div role="list" className="divide-y divide-grid">
        {account.tasks.map((t) => (
          <div key={t.id}>
            <TaskRow task={t} onChange={refresh} />
            {isOpen(t) &&
              (editing === t.id ? (
                <EditTask
                  task={t}
                  onCancel={() => setEditing(null)}
                  onSaved={() => {
                    setEditing(null);
                    refresh();
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
    </Panel>
  );
}

function Audit({ id }: { id: string }) {
  const { data, error } = useApi<AuditEntry[]>(`/accounts/${id}/audit?limit=500`);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={6} />;
  return (
    <Panel title="Audit log" description="Who changed what, when, and why. Kept for every record.">
      {data.length === 0 ? (
        <Empty>No audited changes.</Empty>
      ) : (
        <ul className="divide-y divide-grid" data-testid="audit">
          {data.map((e) => (
            <li key={e.id} className="space-y-1.5 py-3 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-fg">{e.action}</span>
                <span className="text-xs text-fg-3">
                  {formatDate(e.occurred_at, true)} · {e.source}
                </span>
              </div>
              {e.reason && <p className="text-xs text-fg-2">Reason: {e.reason}</p>}
              {e.new_value && <pre className="overflow-x-auto rounded-lg bg-sunken p-2.5 font-mono text-[11.5px] text-fg-2">{JSON.stringify(e.new_value, null, 2)}</pre>}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export default function AccountPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session } = useSession();
  const { data: account, error, mutate } = useApi<Account360>(`/accounts/${id}`);
  const [tab, setTab] = useTab("overview");
  if (error) return <ErrorNote error={error} />;
  if (!account) return <Skeleton rows={8} />;

  const tabs = [
    { key: "overview", label: "Overview" },
    { key: "leads", label: `Leads (${account.leads.length})` },
    { key: "tasks", label: `Tasks (${account.open_tasks} open)` },
    { key: "timeline", label: "Timeline" },
    ...(can(session, "audit.read") ? [{ key: "audit", label: "Audit" }] : []),
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Account"
        title={
          <span className="flex items-center gap-3">
            <span aria-hidden className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-sm font-semibold text-accent-text">
              {initials(account.name)}
            </span>
            {account.name}
          </span>
        }
        badges={
          <>
            <Badge tone="purple">{label(account.account_type)}</Badge>
            <BandBadge band={account.priority_band} />
          </>
        }
        description={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="inline-flex items-center gap-1.5">
              <Globe aria-hidden className="h-3.5 w-3.5 text-fg-3" />
              {account.primary_domain ?? "No website"}
            </span>
            {account.industry && <span>· {account.industry}</span>}
            <span>· owner {account.owner?.name ?? "unassigned"}</span>
            <span>· next activity {account.next_activity_at ? formatDate(account.next_activity_at) : "none set"}</span>
          </span>
        }
      />
      <Tabs label="Account sections" tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" && <Overview account={account} refresh={() => mutate()} />}
      {tab === "leads" && <Leads account={account} />}
      {tab === "tasks" && <Tasks account={account} refresh={() => mutate()} />}
      {tab === "timeline" && (
        <Panel title="Timeline" description="Newest first. Includes what VROS did on its own, such as research and evidence updates.">
          <Timeline accountId={id} />
        </Panel>
      )}
      {tab === "audit" && <Audit id={id} />}
    </div>
  );
}
