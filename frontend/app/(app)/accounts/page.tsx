"use client";

import Link from "next/link";
import { useState } from "react";

import { BandBadge, Card, Empty, ErrorNote, formatDate, inputClass, label, Loading, PageHeader, Score, Table } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { AccountSummary } from "@/lib/types";

export default function AccountsPage() {
  const [q, setQ] = useState("");
  const [owner, setOwner] = useState("");
  const params = new URLSearchParams({ limit: "200" });
  if (q.trim()) params.set("q", q.trim());
  if (owner) params.set("owner", owner);
  const { data, error } = useApi<AccountSummary[]>(`/accounts?${params}`);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Accounts"
        description="Companies approved into the CRM, with their priority, owner and next activity."
        actions={
          <>
            {/* Plain links: the browser downloads with the session cookie. Exports are audited. */}
            <a href={`/api/v1/accounts/export?format=csv${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ""}`} className="rounded-lg border border-border bg-background px-3.5 py-2 text-sm font-medium shadow-sm hover:bg-surface">Export CSV</a>
            <a href={`/api/v1/accounts/export?format=json${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ""}`} className="rounded-lg border border-border bg-background px-3.5 py-2 text-sm font-medium shadow-sm hover:bg-surface">Export JSON</a>
          </>
        }
      />
      <Card>
        <div className="mb-4 flex flex-wrap gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or domain" aria-label="Search accounts" className={`${inputClass} max-w-xs`} />
          <select value={owner} onChange={(e) => setOwner(e.target.value)} aria-label="Owner" className={`${inputClass} max-w-[12rem]`}>
            <option value="">Any owner</option>
            <option value="me">Mine</option>
            <option value="unassigned">Unassigned</option>
          </select>
        </div>
        {error && <ErrorNote error={error} />}
        {!data && !error && <Loading />}
        {data && data.length === 0 && <Empty>No accounts yet. Approve a researched prospect to create one.</Empty>}
        {data && data.length > 0 && (
          <Table testId="accounts">
            <thead>
              <tr>
                <th>Account</th>
                <th>Type</th>
                <th>Priority</th>
                <th>Owner</th>
                <th>Next activity</th>
                <th>Open tasks</th>
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td>
                    <Link href={`/accounts/${a.id}`} className="font-medium hover:text-accent">{a.name}</Link>
                    <div className="text-xs text-muted">{a.primary_domain ?? "—"}{a.industry ? ` · ${a.industry}` : ""}</div>
                  </td>
                  <td>{label(a.account_type)}</td>
                  <td><span className="flex items-center gap-2"><BandBadge band={a.priority_band} /><Score value={a.priority_score} className="font-medium" /></span></td>
                  <td>{a.owner?.name ?? <span className="text-muted">Unassigned</span>}</td>
                  <td className="whitespace-nowrap">{formatDate(a.next_activity_at)}</td>
                  <td className="tabular-nums">{a.open_tasks}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
