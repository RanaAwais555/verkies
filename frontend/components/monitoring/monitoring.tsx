"use client";

import { Check, Eye, EyeOff, Radar, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge, Button, Empty, ErrorNote, Panel, Skeleton, SourceLink, Table, type Tone } from "@/components/ui";
import { api } from "@/lib/client";
import { formatDate, label, relativeDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { MonitorAlert, WatchedAccount } from "@/lib/types";

const KIND: Record<string, { label: string; tone: Tone }> = {
  job_posting: { label: "Hiring", tone: "accent" },
  news: { label: "News", tone: "blue" },
  registry: { label: "Companies House", tone: "purple" },
};

/** Watch or stop watching an account; when watching, check its sources now. */
export function WatchButton({ accountId, watching, onChange }: { accountId: string; watching: boolean; onChange: () => void }) {
  const { busy, error, run } = useAction();
  const [queued, setQueued] = useState(false);
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button
        busy={busy}
        icon={watching ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        onClick={async () => {
          if (await run(() => api(`/accounts/${accountId}/watch`, { method: watching ? "DELETE" : "PUT" }).then(() => true))) onChange();
        }}
      >
        {watching ? "Stop watching" : "Watch"}
      </Button>
      {watching && (
        <Button
          variant="ghost"
          icon={<RefreshCw className="h-4 w-4" />}
          disabled={queued}
          onClick={async () => {
            if (await run(() => api(`/accounts/${accountId}/monitor/check`, { method: "POST" }).then(() => true))) setQueued(true);
          }}
        >
          {queued ? "Check queued" : "Check now"}
        </Button>
      )}
      <ErrorNote error={error} />
    </span>
  );
}

function AlertRow({ alert, showAccount }: { alert: MonitorAlert; showAccount: boolean }) {
  const { busy, run } = useAction();
  const kind = KIND[alert.kind] ?? { label: label(alert.kind), tone: "neutral" as Tone };
  return (
    <li className="flex flex-wrap items-start gap-3 py-3 first:pt-0 last:pb-0" data-testid="monitor-alert">
      <Badge tone={kind.tone}>{kind.label}</Badge>
      <span className="min-w-0 flex-1 space-y-0.5">
        <span className={alert.reviewed ? "block text-[13px] text-fg-3" : "block text-[13px] font-medium text-fg"}>{alert.title}</span>
        <span className="block text-xs text-fg-3">
          {showAccount && (
            <>
              <Link href={`/accounts/${alert.account_id}`} className="text-accent-text hover:underline">
                {alert.account_name}
              </Link>
              {" · "}
            </>
          )}
          {alert.signal_label ?? (alert.signal ? label(alert.signal) : "Signal")}
          {alert.happened_on && ` · ${formatDate(alert.happened_on)}`} · found {relativeDate(alert.created_at).toLowerCase()}
        </span>
        <SourceLink url={alert.source_url} />
      </span>
      {!alert.reviewed && (
        <Button
          className="h-7 px-2.5 text-xs"
          busy={busy}
          icon={<Check className="h-3.5 w-3.5" />}
          onClick={() => run(() => api(`/monitoring/alerts/${alert.id}/review`, { method: "POST" }))}
        >
          Reviewed
        </Button>
      )}
    </li>
  );
}

/** What monitoring found: new signals on watched accounts, newest first. */
export function AlertList({ query, showAccount = true, empty }: { query: string; showAccount?: boolean; empty: string }) {
  const { data, error } = useApi<MonitorAlert[]>(`/monitoring/alerts${query ? `?${query}` : ""}`);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={3} />;
  if (data.length === 0) return <Empty icon={<Radar className="h-4 w-4" />}>{empty}</Empty>;
  return (
    <ul className="divide-y divide-grid" data-testid="monitor-alerts">
      {data.map((a) => (
        <AlertRow key={a.id} alert={a} showAccount={showAccount} />
      ))}
    </ul>
  );
}

/** The accounts someone watches: when each was last checked and what is waiting. */
export function WatchedTable({ mine }: { mine: boolean }) {
  const { data, error, mutate } = useApi<WatchedAccount[]>(`/monitoring/watched?mine=${mine}`);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={3} />;
  if (data.length === 0)
    return (
      <Empty icon={<Eye className="h-4 w-4" />}>
        {mine ? "You are not watching any account. Use Watch on an account to follow it." : "Nobody is watching an account yet."}
      </Empty>
    );
  return (
    <Table testId="watched">
      <thead>
        <tr>
          <th>Account</th>
          <th>Last checked</th>
          <th className="text-right">New alerts</th>
          <th className="text-right">Watchers</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {data.map((w) => (
          <tr key={w.account_id} data-testid="watched-row">
            <td className="min-w-[12rem]">
              <Link href={`/accounts/${w.account_id}`} className="font-medium text-fg hover:text-accent-text hover:underline">
                {w.name}
              </Link>
              <span className="block text-xs text-fg-3">{w.primary_domain ?? label(w.account_type)}</span>
            </td>
            <td className="whitespace-nowrap text-fg-2" title={formatDate(w.last_checked_at, true)}>
              {w.last_checked_at ? relativeDate(w.last_checked_at) : <span className="text-fg-3">Not yet</span>}
            </td>
            <td className="tabular text-right">{w.open_alerts > 0 ? <Badge tone="accent">{w.open_alerts}</Badge> : <span className="text-fg-3">0</span>}</td>
            <td className="tabular text-right text-fg-2">{w.watchers}</td>
            <td className="text-right">
              <WatchButton accountId={w.account_id} watching={w.watching} onChange={() => mutate()} />
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

/** Monitoring on the account page: what was found here. */
export function AccountAlerts({ accountId }: { accountId: string }) {
  return (
    <Panel
      title="Monitoring"
      description="New hiring, news and Companies House filings found when VROS re-checked this account's own sources."
      testId="account-monitoring"
    >
      <AlertList query={`account_id=${accountId}`} showAccount={false} empty="Nothing new found yet. Watched accounts are checked every morning." />
    </Panel>
  );
}
