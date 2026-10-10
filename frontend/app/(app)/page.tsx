"use client";

import { AlertTriangle, ArrowRight, ChevronDown, Inbox, ListChecks } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { TaskRow } from "@/components/crm/tasks";
import { ResearchForm } from "@/components/research/research-form";
import { Badge, BandBadge, Empty, ErrorNote, LinkButton, MetricStrip, PageHeader, Panel, ScoreChip, Skeleton, TextLink, type Metric } from "@/components/ui";
import { isOverdue } from "@/lib/format";
import { can, useApi, useSession } from "@/lib/hooks";
import type { Opportunity, QueueItem, Task } from "@/lib/types";
import { REJECTION_REASONS } from "@/lib/types";

const QUEUE = "/prospects";
const MY_TASKS = "/tasks?mine=true&status=open";
const ATTENTION = "/opportunities/requires-attention";

const FIRST = 8;

// Priority bands are ordered, so they share one hue stepped from strong to faint (dataviz: sequential).
const BANDS: { key: string; label: string; mix: number }[] = [
  { key: "hot", label: "Hot", mix: 100 },
  { key: "high", label: "High", mix: 78 },
  { key: "qualified", label: "Qualified", mix: 56 },
  { key: "monitor", label: "Monitor", mix: 36 },
  { key: "reject", label: "Reject", mix: 18 },
];
const bandFill = (mix: number) => `color-mix(in srgb, var(--accent) ${mix}%, var(--sunken))`;

/** How the queue splits across priority bands: one bar, a legend with counts, no colour-only meaning. */
function BandSplit({ items }: { items: QueueItem[] }) {
  const counts = BANDS.map((b) => ({ ...b, n: items.filter((i) => i.priority_band === b.key).length }));
  const unknown = items.length - counts.reduce((sum, b) => sum + b.n, 0);
  const shown = counts.filter((b) => b.n > 0);
  return (
    <figure className="mb-4 space-y-2.5" aria-label="Review queue by priority band">
      <div className="flex h-2.5 gap-[2px] overflow-hidden rounded-full bg-track">
        {shown.map((b) => (
          <span key={b.key} title={`${b.label}: ${b.n}`} className="h-full first:rounded-l-full last:rounded-r-full" style={{ width: `${(b.n / items.length) * 100}%`, background: bandFill(b.mix) }} />
        ))}
      </div>
      <figcaption className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-3">
        {shown.map((b) => (
          <span key={b.key} className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-2 rounded-[3px]" style={{ background: bandFill(b.mix) }} />
            {b.label} <span className="tabular font-medium text-fg">{b.n}</span>
          </span>
        ))}
        {unknown > 0 && (
          <span>
            Unscored <span className="tabular font-medium text-fg">{unknown}</span>
          </span>
        )}
      </figcaption>
    </figure>
  );
}

function ReviewQueue() {
  const { data, error } = useApi<QueueItem[]>(QUEUE, { refreshInterval: 15000 });
  const [all, setAll] = useState(false);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={4} />;
  if (data.length === 0) return <Empty icon={<Inbox className="h-4 w-4" />}>Nothing to review. Research a company to fill the queue.</Empty>;
  const visible = all ? data : data.slice(0, FIRST);
  return (
    <>
    <BandSplit items={data} />
    <ul className="-mx-4 divide-y divide-grid border-t border-grid" data-testid="review-queue">
      {visible.map((item) => (
        <li key={item.run_id}>
          <Link href={`/research/${item.run_id}`} className="group grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-1.5 px-4 py-3 transition-colors hover:bg-surface-2 sm:grid-cols-[auto_minmax(0,1fr)_auto]">
            <ScoreChip value={item.priority_score} />
            <span className="min-w-0">
              <span className="block truncate font-medium text-fg group-hover:text-accent-text" title={item.company ?? item.domain}>
                {item.company ?? item.domain}
              </span>
              <span className="block text-xs text-fg-3">{item.domain}</span>
            </span>
            <span className="col-start-2 flex flex-wrap items-center gap-1.5 sm:col-start-3 sm:justify-end">
              {item.hard_reject ? (
                <Badge tone="red">Suggest reject: {REJECTION_REASONS[item.recommended_rejection ?? ""] ?? "see brief"}</Badge>
              ) : item.qualifies ? (
                <Badge tone="green">Qualifies</Badge>
              ) : (
                <Badge>Below threshold</Badge>
              )}
              {item.possible_duplicates.length > 0 && <Badge tone="purple">Possible duplicate</Badge>}
              <BandBadge band={item.priority_band} />
            </span>
            {item.next_action && <span className="col-start-2 truncate text-xs text-fg-2 sm:col-end-4">Next: {item.next_action}</span>}
          </Link>
        </li>
      ))}
    </ul>
    {data.length > FIRST && (
      <button
        type="button"
        onClick={() => setAll(!all)}
        aria-expanded={all}
        className="-mx-4 -mb-4 flex w-[calc(100%+2rem)] items-center justify-center gap-1.5 border-t border-grid py-2.5 text-[13px] text-fg-2 transition-colors hover:bg-surface-2 hover:text-fg"
      >
        {all ? "Show the top " + FIRST : `Show all ${data.length}`}
        <ChevronDown aria-hidden className={`h-4 w-4 transition-transform duration-200 ease-spring ${all ? "rotate-180" : ""}`} />
      </button>
    )}
    </>
  );
}

function MyTasks() {
  const { data, error, mutate } = useApi<Task[]>(MY_TASKS);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={3} />;
  if (data.length === 0) return <Empty icon={<ListChecks className="h-4 w-4" />}>No open tasks.</Empty>;
  return (
    <div role="list" className="divide-y divide-grid" data-testid="my-tasks">
      {data.map((t) => (
        <TaskRow key={t.id} task={t} showAccount onChange={() => mutate()} />
      ))}
    </div>
  );
}

function Attention() {
  const { data, error } = useApi<Opportunity[]>(ATTENTION);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={3} />;
  if (data.length === 0) return <Empty>Every opportunity has an owned, dated next action.</Empty>;
  return (
    <ul className="divide-y divide-grid" data-testid="attention">
      {data.map((o) => (
        <li key={o.id} className="flex gap-3 py-3 text-[13px] first:pt-0 last:pb-0">
          <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
          <div className="min-w-0">
            <TextLink href={`/accounts/${o.account_id}`}>{o.account_name ?? "Account"}</TextLink>
            <span className="text-fg-3"> · {o.name}</span>
            <p className="mt-0.5 text-xs text-bad">{o.requires_attention.join("; ")}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Headline counts from the same requests the panels below make, so they are fetched once. */
function Numbers({ reviewer, member }: { reviewer: boolean; member: boolean }) {
  const { data: queue } = useApi<QueueItem[]>(reviewer ? QUEUE : null, { refreshInterval: 15000 });
  const { data: tasks } = useApi<Task[]>(member ? MY_TASKS : null);
  const { data: attention } = useApi<Opportunity[]>(member ? ATTENTION : null);
  const overdue = tasks?.filter((t) => isOverdue(t.due_at)).length ?? 0;
  const count = (list: unknown[] | undefined) => (list ? list.length : "…");
  const metrics: Metric[] = [];
  if (reviewer) metrics.push({ label: "Awaiting review", value: count(queue), hint: "Researched prospects to approve or reject", tone: "accent" });
  if (member) {
    metrics.push({ label: "My open tasks", value: count(tasks), hint: overdue ? `${overdue} overdue` : "None overdue", tone: overdue ? "red" : "neutral" });
    metrics.push({ label: "Without a next action", value: count(attention), hint: "Opportunities with no owned, dated task", tone: attention?.length ? "amber" : "neutral" });
  }
  return metrics.length ? <MetricStrip metrics={metrics} /> : null;
}

export default function CommandCenterPage() {
  const { data: session } = useSession();
  const reviewer = can(session, "prospects.review");
  const member = can(session, "accounts.read", "accounts.read_own");
  const firstName = session?.user.name.split(" ")[0];
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={today}
        title="Command Center"
        description={firstName ? `Good to see you, ${firstName}. Here is what needs you today.` : undefined}
      />

      <Numbers reviewer={reviewer} member={member} />

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,1fr)]">
        <div className="flex min-w-0 flex-col gap-5">
          {can(session, "research.run") && (
            <Panel title="Research a company" description="Paste a website. VROS reads the public site and registries, then writes an evidenced brief.">
              <ResearchForm />
            </Panel>
          )}
          {reviewer && (
            <Panel
              primary
              title="Review queue"
              description="Highest priority first. Open one to read the brief and decide."
              actions={
                <LinkButton href="/research" variant="ghost" icon={<ArrowRight className="h-4 w-4" />}>
                  All research
                </LinkButton>
              }
            >
              <ReviewQueue />
            </Panel>
          )}
        </div>
        {member && (
          <aside className="flex min-w-0 flex-col gap-5 xl:sticky xl:top-20" aria-label="Your work">
            <Panel title="My open tasks" collapsible>
              <MyTasks />
            </Panel>
            <Panel title="Opportunities requiring attention" collapsible>
              <Attention />
            </Panel>
          </aside>
        )}
      </div>
    </div>
  );
}
