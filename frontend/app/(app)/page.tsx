"use client";

import Link from "next/link";

import { NewResearchForm } from "@/components/research-form";
import { TaskRow } from "@/components/tasks";
import { Badge, BandBadge, Card, Empty, ErrorNote, isOverdue, Loading, PageHeader, Score, Stat, TextLink } from "@/components/ui";
import { can, useApi, useSession } from "@/lib/hooks";
import type { Opportunity, QueueItem, Task } from "@/lib/types";
import { REJECTION_REASONS } from "@/lib/types";

function ReviewQueue() {
  const { data, error } = useApi<QueueItem[]>("/prospects", { refreshInterval: 15000 });
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  if (data.length === 0) return <Empty>Nothing to review. Research a company to fill the queue.</Empty>;
  return (
    <ul className="-mx-5 -my-5 divide-y divide-border" data-testid="review-queue">
      {data.map((item) => (
        <li key={item.run_id} className="px-5 py-3 transition-colors hover:bg-surface/50">
          <Link href={`/research/${item.run_id}`} className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{item.company ?? item.domain}</span>
            <span className="text-xs text-muted">{item.domain}</span>
            <span className="ml-auto flex items-center gap-2 text-sm">
              {item.hard_reject ? (
                <Badge tone="red">Suggest reject: {REJECTION_REASONS[item.recommended_rejection ?? ""] ?? "see brief"}</Badge>
              ) : item.qualifies ? (
                <Badge tone="green">Qualifies</Badge>
              ) : (
                <Badge>Below threshold</Badge>
              )}
              {item.possible_duplicates.length > 0 && <Badge tone="purple">Possible duplicate</Badge>}
              <BandBadge band={item.priority_band} />
              <Score value={item.priority_score} className="w-8 text-right font-semibold" />
            </span>
          </Link>
          {item.next_action && <p className="mt-1 text-xs text-muted">Next: {item.next_action}</p>}
        </li>
      ))}
    </ul>
  );
}

function MyTasks() {
  const { data, error, mutate } = useApi<Task[]>("/tasks?mine=true&status=open");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  if (data.length === 0) return <Empty>No open tasks.</Empty>;
  return (
    <div role="list" className="-my-2 divide-y divide-border" data-testid="my-tasks">
      {data.map((t) => <TaskRow key={t.id} task={t} showAccount onChange={() => mutate()} />)}
    </div>
  );
}

function Attention() {
  const { data, error } = useApi<Opportunity[]>("/opportunities/requires-attention");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  if (data.length === 0) return <Empty>Every opportunity has an owned, dated next action.</Empty>;
  return (
    <ul className="divide-y divide-border" data-testid="attention">
      {data.map((o) => (
        <li key={o.id} className="py-2.5 text-sm first:pt-0 last:pb-0">
          <TextLink href={`/accounts/${o.account_id}`}>{o.account_name ?? "Account"}</TextLink>
          <span className="text-muted"> · {o.name}</span>
          <p className="mt-0.5 text-xs text-red-600 dark:text-red-400">{o.requires_attention.join("; ")}</p>
        </li>
      ))}
    </ul>
  );
}

/** Headline counts, from the same requests the cards below make (fetched once, shared). */
function Stats({ reviewer, member }: { reviewer: boolean; member: boolean }) {
  const { data: queue } = useApi<QueueItem[]>(reviewer ? "/prospects" : null, { refreshInterval: 15000 });
  const { data: tasks } = useApi<Task[]>(member ? "/tasks?mine=true&status=open" : null);
  const { data: attention } = useApi<Opportunity[]>(member ? "/opportunities/requires-attention" : null);
  const overdue = tasks?.filter((t) => isOverdue(t.due_at)).length ?? 0;
  const count = (list: unknown[] | undefined) => (list ? list.length : "…");
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {reviewer && <Stat label="Awaiting review" value={count(queue)} hint="Researched prospects to approve or reject" tone="accent" />}
      {member && <Stat label="My open tasks" value={count(tasks)} hint={overdue ? `${overdue} overdue` : "None overdue"} tone={overdue ? "red" : "neutral"} />}
      {member && (
        <Stat
          label="Without a next action"
          value={count(attention)}
          hint="Opportunities with no owned, dated task"
          tone={attention?.length ? "amber" : "neutral"}
        />
      )}
    </div>
  );
}

export default function HomePage() {
  const { data: session } = useSession();
  const reviewer = can(session, "prospects.review");
  const member = can(session, "accounts.read", "accounts.read_own");
  const firstName = session?.user.name.split(" ")[0];
  return (
    <div className="space-y-6">
      <PageHeader title="Home" description={firstName ? `Welcome back, ${firstName}. Here is what needs you today.` : undefined} />
      <Stats reviewer={reviewer} member={member} />
      {can(session, "research.run") && (
        <Card title="Research a company" description="Paste a website. VROS reads the public site and registries, then writes an evidenced brief.">
          <NewResearchForm />
        </Card>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        {reviewer && (
          <Card title="Review queue" className="lg:col-span-2">
            <ReviewQueue />
          </Card>
        )}
        {member && (
          <Card title="My open tasks">
            <MyTasks />
          </Card>
        )}
        {member && (
          <Card title="Opportunities requiring attention">
            <Attention />
          </Card>
        )}
      </div>
    </div>
  );
}
