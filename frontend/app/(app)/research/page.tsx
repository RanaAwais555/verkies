"use client";

import Link from "next/link";
import { useState } from "react";

import { NewResearchForm } from "@/components/research-form";
import { Card, Empty, ErrorNote, formatDate, inputClass, Loading, PageHeader, StatusBadge, Table } from "@/components/ui";
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
      <PageHeader title="Research" description="Every company researched by the team, with its progress and the decision taken." />
      {can(session, "research.run") && (
        <Card title="New research">
          <NewResearchForm />
        </Card>
      )}
      <Card title="All research runs">
        <div className="mb-4 flex flex-wrap gap-2">
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
          <Table testId="runs">
            <thead>
              <tr>
                <th>Company website</th>
                <th>Status</th>
                <th>Decision</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {data.map((run) => (
                <tr key={run.id}>
                  <td>
                    <Link href={`/research/${run.id}`} className="font-medium hover:text-accent">{run.normalised_domain}</Link>
                  </td>
                  <td>
                    <StatusBadge status={run.status} />
                    {run.status !== "completed" && run.status !== "failed" && run.status !== "cancelled" && (
                      <span className="ml-2 text-xs text-muted">{run.progress_pct}%</span>
                    )}
                  </td>
                  <td>
                    <StatusBadge status={run.review_status} />
                    {run.rejection_reason && <span className="ml-2 text-xs text-muted">{REJECTION_REASONS[run.rejection_reason]}</span>}
                  </td>
                  <td className="whitespace-nowrap text-muted">{formatDate(run.created_at, true)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
