"use client";

import Link from "next/link";
import { useState } from "react";

import { BandBadge, Card, Empty, ErrorNote, formatDate, inputClass, label, Loading, Score } from "@/components/ui";
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
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Accounts</h1>
        <span className="ml-auto flex gap-3 text-sm">
          {/* Plain links: the browser downloads with the session cookie. Exports are audited. */}
          <a href={`/api/v1/accounts/export?format=csv${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ""}`} className="underline">Export CSV</a>
          <a href={`/api/v1/accounts/export?format=json${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ""}`} className="underline">Export JSON</a>
        </span>
      </div>
      <Card>
        <div className="mb-3 flex flex-wrap gap-2">
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
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="accounts">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-1 pr-3 font-medium">Account</th>
                  <th className="py-1 pr-3 font-medium">Type</th>
                  <th className="py-1 pr-3 font-medium">Priority</th>
                  <th className="py-1 pr-3 font-medium">Owner</th>
                  <th className="py-1 pr-3 font-medium">Next activity</th>
                  <th className="py-1 pr-3 font-medium">Open tasks</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.map((a) => (
                  <tr key={a.id}>
                    <td className="py-1.5 pr-3">
                      <Link href={`/accounts/${a.id}`} className="font-medium hover:underline">{a.name}</Link>
                      <div className="text-xs text-muted">{a.primary_domain ?? "—"}{a.industry ? ` · ${a.industry}` : ""}</div>
                    </td>
                    <td className="py-1.5 pr-3">{label(a.account_type)}</td>
                    <td className="py-1.5 pr-3"><span className="flex items-center gap-2"><BandBadge band={a.priority_band} /><Score value={a.priority_score} /></span></td>
                    <td className="py-1.5 pr-3">{a.owner?.name ?? <span className="text-muted">Unassigned</span>}</td>
                    <td className="py-1.5 pr-3">{formatDate(a.next_activity_at)}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{a.open_tasks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
