"use client";

import { Bell, CheckCheck } from "lucide-react";
import Link from "next/link";

import { Button, Checkbox, Empty, ErrorNote, PageHeader, Panel, Skeleton } from "@/components/ui";
import { api } from "@/lib/client";
import { relativeDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { AppNotification, NotificationKind } from "@/lib/types";

function Row({ n }: { n: AppNotification }) {
  const { run } = useAction();
  const markRead = () => (n.read ? undefined : run(() => api(`/notifications/${n.id}/read`, { method: "POST" })));
  const title = <span className={n.read ? "text-fg-2" : "font-medium text-fg"}>{n.title}</span>;
  return (
    <li className="flex items-start gap-3 py-3 first:pt-0 last:pb-0" data-testid="notification">
      <span aria-hidden className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.read ? "bg-transparent" : "bg-accent"}`} />
      <span className="min-w-0 flex-1 space-y-0.5 text-[13px]">
        {n.link ? (
          <Link href={n.link} onClick={markRead} className="block hover:underline">
            {title}
          </Link>
        ) : (
          <span className="block">{title}</span>
        )}
        {n.body && <span className="block break-words text-xs text-fg-3">{n.body}</span>}
        <span className="block text-xs text-fg-3">{relativeDate(n.created_at)}</span>
      </span>
      {!n.read && (
        <Button variant="ghost" className="h-7 px-2.5 text-xs" onClick={markRead}>
          Mark read
        </Button>
      )}
    </li>
  );
}

function Preferences() {
  const { data, error, mutate } = useApi<NotificationKind[]>("/notifications/preferences");
  const { error: saveError, run } = useAction();
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={2} />;
  const save = async (kind: string, on: boolean) => {
    const next = data.map((k) => (k.kind === kind ? { ...k, on } : k));
    void mutate(next, { revalidate: false }); // show the change at once
    const off = next.filter((k) => !k.on).map((k) => k.kind);
    if (!(await run(() => api("/notifications/preferences", { method: "PUT", body: { off } })))) void mutate();
  };
  return (
    <div className="space-y-2.5">
      {data.map((k) => (
        <Checkbox key={k.kind} label={k.label} checked={k.on} onChange={(e) => save(k.kind, e.target.checked)} />
      ))}
      <ErrorNote error={saveError} />
    </div>
  );
}

export default function NotificationsPage() {
  const { data, error } = useApi<AppNotification[]>("/notifications");
  const { busy, run } = useAction();
  const unread = data?.filter((n) => !n.read).length ?? 0;
  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="You"
        title="Notifications"
        description="What VROS wants you to know about: monitoring alerts on accounts you watch, and tasks alert rules gave you. Shown here only; nothing is emailed."
      />
      <Panel
        title="Latest"
        actions={
          unread > 0 && (
            <Button busy={busy} icon={<CheckCheck className="h-4 w-4" />} onClick={() => run(() => api("/notifications/read-all", { method: "POST" }))}>
              Mark all read
            </Button>
          )
        }
        testId="notifications"
      >
        {error ? (
          <ErrorNote error={error} />
        ) : !data ? (
          <Skeleton rows={4} />
        ) : data.length === 0 ? (
          <Empty icon={<Bell className="h-4 w-4" />}>No notifications yet.</Empty>
        ) : (
          <ul className="divide-y divide-grid">
            {data.map((n) => (
              <Row key={n.id} n={n} />
            ))}
          </ul>
        )}
      </Panel>
      <Panel title="What to tell me about" description="Switch a kind off and VROS stops creating it for you." className="max-w-2xl">
        <Preferences />
      </Panel>
    </div>
  );
}
