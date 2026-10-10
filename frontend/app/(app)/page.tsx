"use client";

import { AlertTriangle, Inbox, ListChecks } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { TaskRow } from "@/components/crm/tasks";
import { ResearchForm } from "@/components/research/research-form";
import { Badge, BandBadge, Empty, ErrorNote, Panel, ScoreChip, ShowAll, Skeleton, TextLink } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { initials, isOverdue, label } from "@/lib/format";
import { can, useApi, useSession } from "@/lib/hooks";
import type { Opportunity, QueueItem, Session, Task } from "@/lib/types";
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
    <figure className="mb-1 space-y-2.5" aria-label="Review queue by priority band">
      <div className="flex h-2.5 gap-[2px] overflow-hidden rounded-full bg-track">
        {shown.map((b) => (
          <span
            key={b.key}
            title={`${b.label}: ${b.n}`}
            className="h-full first:rounded-l-full last:rounded-r-full"
            style={{ width: `${(b.n / items.length) * 100}%`, background: bandFill(b.mix) }}
          />
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

function QueueRow({ item }: { item: QueueItem }) {
  return (
    <li>
      <Link
        href={`/research/${item.run_id}`}
        className="group grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-1.5 px-5 py-3 transition-colors hover:bg-surface-2 sm:grid-cols-[auto_minmax(0,1fr)_auto]"
      >
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
  );
}

function ReviewQueue() {
  const { data, error } = useApi<QueueItem[]>(QUEUE, { refreshInterval: 15000 });
  const [all, setAll] = useState(false);
  const more = !!data && data.length > FIRST;
  return (
    <Panel
      title="Review queue"
      description="Highest priority first. Open one to read the brief and decide."
      footer={
        more && (
          <ShowAll onClick={() => setAll(!all)} expanded={all}>
            {all ? `Show the top ${FIRST}` : `Show all ${data.length}`}
          </ShowAll>
        )
      }
    >
      {error && <ErrorNote error={error} />}
      {!data && !error && <Skeleton rows={4} />}
      {data?.length === 0 && <Empty icon={<Inbox className="h-4 w-4" />}>Nothing to review. Research a company to fill the queue.</Empty>}
      {data && data.length > 0 && (
        <>
          <BandSplit items={data} />
          <ul className="-mx-5 -mb-4 mt-3 divide-y divide-grid border-t border-grid" data-testid="review-queue">
            {(all ? data : data.slice(0, FIRST)).map((item) => (
              <QueueRow key={item.run_id} item={item} />
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}

function MyTasks() {
  const { data, error, mutate } = useApi<Task[]>(MY_TASKS);
  return (
    <Panel title="My open tasks" footer={data && data.length > 0 && <ShowAll href="/tasks">All my tasks</ShowAll>}>
      {error && <ErrorNote error={error} />}
      {!data && !error && <Skeleton rows={3} />}
      {data?.length === 0 && <Empty icon={<ListChecks className="h-4 w-4" />}>No open tasks.</Empty>}
      {data && data.length > 0 && (
        <div role="list" className="divide-y divide-grid" data-testid="my-tasks">
          {data.map((t) => (
            <TaskRow key={t.id} task={t} showAccount onChange={() => mutate()} />
          ))}
        </div>
      )}
    </Panel>
  );
}

function Attention() {
  const { data, error } = useApi<Opportunity[]>(ATTENTION);
  return (
    <Panel title="Needs a next action" description="Opportunities without an owned, dated task.">
      {error && <ErrorNote error={error} />}
      {!data && !error && <Skeleton rows={3} />}
      {data?.length === 0 && <Empty>Every opportunity has an owned, dated next action.</Empty>}
      {data && data.length > 0 && (
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
      )}
    </Panel>
  );
}

function CountRow({ label: text, value, tone, href }: { label: string; value: ReactNode; tone?: "accent" | "red" | "amber"; href: string }) {
  return (
    <Link href={href} className="flex items-center justify-between gap-3 px-4 py-2.5 text-[13px] transition-colors hover:bg-surface-2">
      <span className="text-fg-2">{text}</span>
      <span
        className={cx(
          "tabular font-semibold",
          tone === "accent" ? "text-accent-text" : tone === "red" ? "text-bad" : tone === "amber" ? "text-warn" : "text-fg",
        )}
      >
        {value}
      </span>
    </Link>
  );
}

/** The left rail: who you are and the counts that matter today, like a LinkedIn feed's profile card. */
function YouCard({ session, reviewer, member }: { session: Session; reviewer: boolean; member: boolean }) {
  const { data: queue } = useApi<QueueItem[]>(reviewer ? QUEUE : null, { refreshInterval: 15000 });
  const { data: tasks } = useApi<Task[]>(member ? MY_TASKS : null);
  const { data: attention } = useApi<Opportunity[]>(member ? ATTENTION : null);
  const overdue = tasks?.filter((t) => isOverdue(t.due_at)).length ?? 0;
  const count = (list: unknown[] | undefined) => (list ? list.length : "…");
  const { user } = session;
  return (
    <section className="lift overflow-hidden rounded-xl border border-border/80 bg-surface" aria-label="You">
      <div
        aria-hidden
        className="h-14"
        style={{
          background:
            "radial-gradient(240px 90px at 85% 0%, color-mix(in srgb, var(--violet) 34%, transparent), transparent 70%), " +
            "radial-gradient(260px 110px at 10% 120%, color-mix(in srgb, var(--accent) 42%, transparent), transparent 72%), " +
            "color-mix(in srgb, var(--accent) 10%, var(--surface-2))",
        }}
      />
      <div className="px-4 pb-4 text-center">
        <span
          aria-hidden
          className="mx-auto -mt-8 grid h-16 w-16 place-items-center rounded-full border-4 border-surface bg-accent-soft text-lg font-semibold text-accent-text"
        >
          {initials(user.name)}
        </span>
        <p className="mt-2 font-semibold text-fg">{user.name}</p>
        <p className="text-xs text-fg-3">{user.roles.map(label).join(" · ")}</p>
      </div>
      <div className="divide-y divide-grid border-t border-grid">
        {reviewer && <CountRow label="Awaiting review" value={count(queue)} tone="accent" href="/research" />}
        {member && <CountRow label="My open tasks" value={count(tasks)} href="/tasks" />}
        {member && overdue > 0 && <CountRow label="Overdue" value={overdue} tone="red" href="/tasks" />}
        {member && <CountRow label="Need a next action" value={count(attention)} tone={attention?.length ? "amber" : undefined} href="/accounts" />}
      </div>
    </section>
  );
}

export default function CommandCenterPage() {
  const { data: session } = useSession();
  const reviewer = can(session, "prospects.review");
  const member = can(session, "accounts.read", "accounts.read_own");
  const firstName = session?.user.name.split(" ")[0];
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="space-y-4">
      <div className="space-y-0.5">
        <p className="text-xs font-medium uppercase tracking-[0.11em] text-fg-3">{today}</p>
        <h1 className="text-[22px] font-semibold tracking-[-0.02em] text-fg">Command Center</h1>
        {firstName && <p className="text-[13.5px] text-fg-2">Good to see you, {firstName}. Here is what needs you today.</p>}
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1fr)_320px]">
        {session && (
          <aside className="min-w-0 lg:sticky lg:top-20" aria-label="Your summary">
            <YouCard session={session} reviewer={reviewer} member={member} />
          </aside>
        )}

        <div className="flex min-w-0 flex-col gap-4">
          {can(session, "research.run") && (
            <Panel title="Research a company" description="Paste a website. VROS reads the public site and registries, then writes an evidenced brief.">
              <ResearchForm />
            </Panel>
          )}
          {reviewer && <ReviewQueue />}
        </div>

        {member && (
          <aside className="flex min-w-0 flex-col gap-4 lg:col-start-2 xl:sticky xl:top-20 xl:col-start-3 xl:row-start-1" aria-label="Your work">
            <MyTasks />
            <Attention />
          </aside>
        )}
      </div>
    </div>
  );
}
