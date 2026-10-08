"use client";

import Link from "next/link";

import { NewResearchForm } from "@/components/research-form";
import { TaskRow } from "@/components/tasks";
import { Badge, BandBadge, Card, Empty, ErrorNote, Loading, Score, TextLink } from "@/components/ui";
import { can, useApi, useSession } from "@/lib/hooks";
import type { Opportunity, QueueItem, Task } from "@/lib/types";
import { REJECTION_REASONS } from "@/lib/types";

function ReviewQueue() {
  const { data, error } = useApi<QueueItem[]>("/prospects", { refreshInterval: 15000 });
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  if (data.length === 0) return <Empty>Nothing to review. Research a company to fill the queue.</Empty>;
  return (
    <ul className="divide-y divide-border" data-testid="review-queue">
      {data.map((item) => (
        <li key={item.run_id} className="py-2">
          <Link href={`/research/${item.run_id}`} className="flex flex-wrap items-center gap-2 hover:underline">
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
              <Score value={item.priority_score} />
            </span>
          </Link>
          {item.next_action && <p className="mt-0.5 text-xs text-muted">Next: {item.next_action}</p>}
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
    <div role="list" className="divide-y divide-border" data-testid="my-tasks">
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
        <li key={o.id} className="py-2 text-sm">
          <TextLink href={`/accounts/${o.account_id}`}>{o.account_name ?? "Account"}</TextLink>
          <span className="text-muted"> · {o.name}</span>
          <p className="text-xs text-red-600">{o.requires_attention.join("; ")}</p>
        </li>
      ))}
    </ul>
  );
}

export default function HomePage() {
  const { data: session } = useSession();
  const reviewer = can(session, "prospects.review");
  const member = can(session, "accounts.read", "accounts.read_own");
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Home</h1>
      {can(session, "research.run") && (
        <Card title="Research a company">
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
