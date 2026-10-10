"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ResearchForm } from "@/components/research/research-form";
import { Empty, ErrorNote, controlClass, PageHeader, Panel, Skeleton, StatusBadge, Table } from "@/components/ui";
import { withQuery } from "@/lib/client";
import { formatDate } from "@/lib/format";
import { can, useApi, useSession } from "@/lib/hooks";
import type { Run } from "@/lib/types";
import { REJECTION_REASONS } from "@/lib/types";

const ACTIVE = new Set(["queued", "running", "retrying"]);

export default function LeadIntelligencePage() {
  const { data: session } = useSession();
  const [q, setQ] = useState("");
  const [review, setReview] = useState("");
  const { data, error } = useApi<Run[]>(withQuery("/research-runs", { limit: 100, q: q.trim(), review_status: review }), { refreshInterval: 5000 });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Revenue"
        title="Lead Intelligence"
        description="Every company researched by the team: its progress, the evidence, and the decision taken. Rejected companies stay here for audit."
      />
      {can(session, "research.run") && (
        <Panel title="New research">
          <ResearchForm />
        </Panel>
      )}
      <Panel
        primary
        title="All research"
        actions={
          <div className="flex flex-wrap gap-2">
            <span className="relative">
              <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-3" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by domain" aria-label="Search by domain" className={`${controlClass} w-56 pl-8`} />
            </span>
            <select value={review} onChange={(e) => setReview(e.target.value)} aria-label="Review status" className={`${controlClass} w-44`}>
              <option value="">Any decision</option>
              <option value="pending">Awaiting review</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
        }
      >
        {error && <ErrorNote error={error} />}
        {!data && !error && <Skeleton rows={6} />}
        {data && data.length === 0 && <Empty>No research matches. Try another domain or decision.</Empty>}
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
                    <Link href={`/research/${run.id}`} className="font-medium text-fg hover:text-accent-text">
                      {run.normalised_domain}
                    </Link>
                  </td>
                  <td>
                    <span className="flex items-center gap-2">
                      <StatusBadge status={run.status} />
                      {ACTIVE.has(run.status) && <span className="tabular text-xs text-fg-3">{run.progress_pct}%</span>}
                    </span>
                  </td>
                  <td>
                    <span className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={run.review_status} />
                      {run.rejection_reason && <span className="text-xs text-fg-3">{REJECTION_REASONS[run.rejection_reason] ?? run.rejection_reason}</span>}
                    </span>
                  </td>
                  <td className="whitespace-nowrap text-fg-3">{formatDate(run.created_at, true)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </div>
  );
}
