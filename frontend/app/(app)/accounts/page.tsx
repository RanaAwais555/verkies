"use client";

import { Download, Search } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { BandBadge, Empty, ErrorNote, controlClass, PageHeader, Panel, ScoreChip, Skeleton, Table } from "@/components/ui";
import { withQuery } from "@/lib/client";
import { formatDate, label, relativeDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AccountSummary } from "@/lib/types";

const exportLink =
  "inline-flex h-9 items-center gap-2 rounded-[9px] border border-border-strong bg-surface-2 px-3.5 text-[13px] font-medium text-fg transition-colors hover:border-accent/60";

export default function AccountsPage() {
  // The command palette can open this page already filtered: /accounts?q=harbour.
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [owner, setOwner] = useState("");
  const [type, setType] = useState("");
  const { data, error } = useApi<AccountSummary[]>(withQuery("/accounts", { limit: 200, q: q.trim(), owner, account_type: type }));
  const search = q.trim() ? `&q=${encodeURIComponent(q.trim())}` : "";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Revenue"
        title="Accounts"
        description="One permanent record per company: priority, owner and what happens next."
        actions={
          <>
            {/* Plain links: the browser downloads with the session cookie. Every export is audited. */}
            <a href={`/api/v1/accounts/export?format=csv${search}`} className={exportLink}>
              <Download aria-hidden className="h-4 w-4" />
              Export CSV
            </a>
            <a href={`/api/v1/accounts/export?format=json${search}`} className={exportLink}>
              <Download aria-hidden className="h-4 w-4" />
              Export JSON
            </a>
          </>
        }
      />
      <Panel
        primary
        title={data ? `${data.length} ${data.length === 1 ? "account" : "accounts"}` : "Loading"}
        actions={
          <div className="flex flex-wrap gap-2">
            <span className="relative">
              <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-3" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or domain" aria-label="Search accounts" className={`${controlClass} w-56 pl-8`} />
            </span>
            <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Account type" className={`${controlClass} w-44`}>
              <option value="">Any type</option>
              <option value="prospect">Prospect</option>
              <option value="qualified_prospect">Qualified prospect</option>
              <option value="opportunity">Opportunity</option>
              <option value="customer">Customer</option>
              <option value="former_customer">Former customer</option>
              <option value="partner">Partner</option>
              <option value="competitor">Competitor</option>
              <option value="suppressed">Suppressed</option>
            </select>
            <select value={owner} onChange={(e) => setOwner(e.target.value)} aria-label="Owner" className={`${controlClass} w-40`}>
              <option value="">Any owner</option>
              <option value="me">Mine</option>
              <option value="unassigned">Unassigned</option>
            </select>
          </div>
        }
      >
        {error && <ErrorNote error={error} />}
        {!data && !error && <Skeleton rows={6} />}
        {data && data.length === 0 && (
          <Empty>{q || owner || type ? "No accounts match these filters." : "No accounts yet. Approve a researched prospect to create one."}</Empty>
        )}
        {data && data.length > 0 && (
          <Table testId="accounts">
            <thead>
              <tr>
                <th>Account</th>
                <th>Type</th>
                <th>Priority</th>
                <th>Owner</th>
                <th>Last activity</th>
                <th>Next activity</th>
                <th className="text-right">Open tasks</th>
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td>
                    <Link href={`/accounts/${a.id}`} className="font-medium text-fg hover:text-accent-text">
                      {a.name}
                    </Link>
                    <div className="text-xs text-fg-3">
                      {a.primary_domain ?? "—"}
                      {a.industry ? ` · ${a.industry}` : ""}
                    </div>
                  </td>
                  <td className="text-fg-2">{label(a.account_type)}</td>
                  <td>
                    <span className="flex items-center gap-2">
                      <ScoreChip value={a.priority_score} />
                      <BandBadge band={a.priority_band} />
                    </span>
                  </td>
                  <td>{a.owner?.name ?? <span className="text-fg-3">Unassigned</span>}</td>
                  <td className="whitespace-nowrap text-fg-3" title={formatDate(a.last_activity_at, true)}>
                    {relativeDate(a.last_activity_at)}
                  </td>
                  <td className="whitespace-nowrap" title={formatDate(a.next_activity_at, true)}>
                    {a.next_activity_at ? formatDate(a.next_activity_at) : <span className="text-bad">None set</span>}
                  </td>
                  <td className="tabular text-right">{a.open_tasks}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </div>
  );
}
