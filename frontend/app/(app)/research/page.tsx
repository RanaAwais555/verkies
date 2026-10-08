"use client";

import Link from "next/link";
import { useState } from "react";

import { NewResearchForm } from "@/components/research-form";
import { Card, Empty, ErrorNote, formatDate, inputClass, Loading, StatusBadge } from "@/components/ui";
import { can, useApi, useSession } from "@/lib/hooks";
import type { Run } from "@/lib/types";
import { REJECTION_REASONS } from "@/lib/types";

export default function ResearchPage() {
  const { data: session } = useSession();
  const [q, setQ] = useState("");
  const [review, setReview] = useState("");
  const params = new URLSearchParams({ limit: "100" });
  if (q.trim()) params.set("q", q.trim());
  if (review) params.set("review_status", review);
  const { data, error } = useApi<Run[]>(`/research-runs?${params}`, { refreshInterval: 5000 });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Research</h1>
      {can(session, "research.run") && (
        <Card title="New research">
          <NewResearchForm />
        </Card>
      )}
      <Card title="All research runs">
        <div className="mb-3 flex flex-wrap gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by domain" aria-label="Search by domain" className={`${inputClass} max-w-xs`} />
          <select value={review} onChange={(e) => setReview(e.target.value)} aria-label="Review status" className={`${inputClass} max-w-[12rem]`}>
            <option value="">Any decision</option>
            <option value="pending">Awaiting review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
        {error && <ErrorNote error={error} />}
        {!data && !error && <Loading />}
        {data && data.length === 0 && <Empty>No research matches.</Empty>}
        {data && data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="runs">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-1 pr-3 font-medium">Domain</th>
                  <th className="py-1 pr-3 font-medium">Status</th>
                  <th className="py-1 pr-3 font-medium">Decision</th>
                  <th className="py-1 pr-3 font-medium">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.map((run) => (
                  <tr key={run.id}>
                    <td className="py-1.5 pr-3">
                      <Link href={`/research/${run.id}`} className="font-medium hover:underline">{run.normalised_domain}</Link>
                    </td>
                    <td className="py-1.5 pr-3">
                      <StatusBadge status={run.status} />
                      {run.status !== "completed" && run.status !== "failed" && run.status !== "cancelled" && (
                        <span className="ml-2 text-xs text-muted">{run.progress_pct}%</span>
                      )}
                    </td>
                    <td className="py-1.5 pr-3">
                      <StatusBadge status={run.review_status} />
                      {run.rejection_reason && <span className="ml-2 text-xs text-muted">{REJECTION_REASONS[run.rejection_reason]}</span>}
                    </td>
                    <td className="py-1.5 pr-3 text-muted">{formatDate(run.created_at, true)}</td>
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
