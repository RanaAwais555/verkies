"use client";

import { AlertTriangle, ArrowRight, Inbox, ListChecks } from "lucide-react";
import Link from "next/link";

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

function ReviewQueue() {
  const { data, error } = useApi<QueueItem[]>(QUEUE, { refreshInterval: 15000 });
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={4} />;
  if (data.length === 0) return <Empty icon={<Inbox className="h-4 w-4" />}>Nothing to review. Research a company to fill the queue.</Empty>;
  return (
    <ul className="-mx-4 -my-4 divide-y divide-grid" data-testid="review-queue">
      {data.map((item) => (
        <li key={item.run_id}>
          <Link href={`/research/${item.run_id}`} className="group flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-3 transition-colors hover:bg-surface-2">
            <ScoreChip value={item.priority_score} />
            <span className="min-w-0">
              <span className="block font-medium text-fg group-hover:text-accent-text">{item.company ?? item.domain}</span>
              <span className="block text-xs text-fg-3">{item.domain}</span>
            </span>
            <span className="ml-auto flex flex-wrap items-center gap-1.5">
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
            {item.next_action && <span className="basis-full pl-[46px] text-xs text-fg-2">Next: {item.next_action}</span>}
          </Link>
        </li>
      ))}
    </ul>
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

      {member && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Panel title="My open tasks" collapsible>
            <MyTasks />
          </Panel>
          <Panel title="Opportunities requiring attention" collapsible>
            <Attention />
          </Panel>
        </div>
      )}
    </div>
  );
}
