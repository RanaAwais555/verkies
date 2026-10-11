"use client";

import { Microscope } from "lucide-react";
import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Badge, Button, ErrorNote, Field, inputClass, PageHeader, Panel, Skeleton, Spinner, StatusBadge, Success, Table, TextLink, type Tone } from "@/components/ui";
import { api } from "@/lib/client";
import { label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { BulkResearchResult, ImportDetail, ImportRow } from "@/lib/types";

const MAX_PER_BATCH = 50;
const ACTIVE_RUN = ["queued", "running", "retrying"];
const RESEARCHABLE = new Set(["new", "possible_duplicate"]);
const STATUS_TONE: Record<ImportRow["status"], Tone> = {
  pending: "neutral",
  new: "green",
  invalid: "red",
  duplicate_in_file: "neutral",
  existing_account: "purple",
  possible_duplicate: "amber",
  already_researched: "neutral",
  suppressed: "red",
  queued: "blue",
  finding_website: "blue",
  no_website: "neutral",
};

function Mapping({ job, onChecked }: { job: ImportDetail; onChecked: (job: ImportDetail) => void }) {
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const mapping = Object.fromEntries(job.fields.map((f) => [f, String(data.get(f) ?? "")]));
    const checked = await run(() => api<ImportDetail>(`/discovery/imports/${job.id}/mapping`, { method: "PUT", body: { mapping } }));
    if (checked) onChecked(checked);
  }

  return (
    <Panel title="Which column is which?" description="Match the file's columns to what VROS needs. Rows are then checked against your accounts." collapsible defaultOpen={job.status === "uploaded"}>
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {job.fields.map((field) => (
            <Field key={field} label={field === "website" ? "Website (required)" : label(field)}>
              <select name={field} defaultValue={job.mapping[field] ?? ""} className={inputClass}>
                <option value="">Not in this file</option>
                {job.columns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </Field>
          ))}
        </div>
        <ErrorNote error={error} />
        <Button type="submit" variant={job.status === "uploaded" ? "primary" : "secondary"} busy={busy}>
          {job.status === "checked" ? "Check again" : "Check rows"}
        </Button>
      </form>
    </Panel>
  );
}

export default function ImportPage() {
  const { id } = useParams<{ id: string }>();
  const { data: job, error, mutate } = useApi<ImportDetail>(`/discovery/imports/${id}`, {
    refreshInterval: (latest) =>
      latest?.status === "running" ? 3000 : latest?.rows.some((r) => r.run_status && ACTIVE_RUN.includes(r.run_status)) ? 5000 : 0,
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<string | null>(null);
  const action = useAction();

  if (error) return <ErrorNote error={error} />;
  if (!job) return <Skeleton rows={8} />;

  const fresh = job.rows.filter((r) => r.status === "new");
  const toggle = (rowId: string) => {
    const next = new Set(selected);
    if (next.has(rowId)) next.delete(rowId);
    else if (next.size < MAX_PER_BATCH) next.add(rowId);
    setSelected(next);
  };

  async function research() {
    setResult(null);
    const out = await action.run(() => api<BulkResearchResult>(`/discovery/imports/${id}/research`, { method: "POST", body: { row_ids: [...selected] } }));
    if (!out) return;
    const skipped = Object.keys(out.skipped).length;
    setResult(
      `Started research on ${out.started.length} compan${out.started.length === 1 ? "y" : "ies"}${skipped ? `; ${skipped} skipped` : ""}${
        out.queue_failures ? `; ${out.queue_failures} could not be queued` : ""
      }.`,
    );
    setSelected(new Set());
    await mutate();
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Discover"
        title={job.kind === "search" ? `Search: ${job.name}` : job.kind === "registry" ? `Companies House: ${job.name}` : job.name}
        description={`${job.row_count} ${job.kind === "search" ? "company websites found" : "rows"}`}
      />
      {job.status === "running" && (
        <div role="status" data-testid="finding-websites" className="flex items-center gap-3 rounded-xl border border-info/30 bg-info-soft px-4 py-3 text-[13px] text-fg">
          <Spinner />
          <span>
            Finding websites: {job.rows.filter((r) => r.status === "finding_website").length} of {job.row_count} left. A site counts only if it shows the
            company&apos;s registered number. This page updates by itself.
          </span>
        </div>
      )}
      {job.kind === "csv_import" && (
        <Mapping
          job={job}
          onChecked={(checked) => {
            setSelected(new Set());
            mutate(checked, { revalidate: false });
          }}
        />
      )}
      {job.status !== "uploaded" && (
        <Panel
          primary
          title="Rows"
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => setSelected(new Set(fresh.slice(0, MAX_PER_BATCH).map((r) => r.id)))}>
                Select new ({Math.min(MAX_PER_BATCH, fresh.length)})
              </Button>
              <Button variant="primary" onClick={research} busy={action.busy} disabled={selected.size === 0} icon={<Microscope className="h-4 w-4" />}>
                Research selected ({selected.size})
              </Button>
            </div>
          }
        >
          <div className="mb-4 flex flex-wrap gap-1.5">
            {Object.entries(job.stats).map(([s, n]) => (
              <Badge key={s} tone={STATUS_TONE[s as ImportRow["status"]] ?? "neutral"}>
                {n} {label(s).toLowerCase()}
              </Badge>
            ))}
          </div>
          <ErrorNote error={action.error} />
          {result && <Success testId="research-result" className="mb-3">{result}</Success>}
          <Table testId="import-rows">
            <thead>
              <tr>
                <th className="w-8">
                  <span className="sr-only">Select</span>
                </th>
                <th>Row</th>
                <th>Company</th>
                <th>Website</th>
                <th>Check</th>
                <th>Research</th>
              </tr>
            </thead>
            <tbody>
              {job.rows.map((r) => (
                <tr key={r.id} className={selected.has(r.id) ? "bg-accent-soft/40" : undefined}>
                  <td>
                    {RESEARCHABLE.has(r.status) && (
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-[var(--accent)]"
                        aria-label={`Select row ${r.row_number}`}
                        checked={selected.has(r.id)}
                        onChange={() => toggle(r.id)}
                      />
                    )}
                  </td>
                  <td className="tabular text-fg-3">{r.row_number}</td>
                  <td>
                    <span className="font-medium text-fg">{r.name ?? "—"}</span>
                    {r.industry && <span className="text-xs text-fg-3"> · {r.industry}</span>}
                    {r.raw.number && (
                      <span className="block text-xs text-fg-3">
                        No. {r.raw.number}
                        {r.raw.locality ? ` · ${r.raw.locality}` : ""}
                      </span>
                    )}
                  </td>
                  <td className="text-fg-2">{r.normalised_domain ?? r.website_url ?? "—"}</td>
                  <td>
                    <Badge tone={STATUS_TONE[r.status]}>{label(r.status)}</Badge>
                    {r.status_detail && <div className="mt-1 max-w-[32ch] text-xs text-fg-3">{r.status_detail}</div>}
                    {r.matched_account_id && (
                      <div className="mt-1">
                        <TextLink href={`/accounts/${r.matched_account_id}`}>Account</TextLink>
                      </div>
                    )}
                  </td>
                  <td>
                    {r.research_run_id ? (
                      <span className="flex items-center gap-1 whitespace-nowrap">
                        {r.run_status && <StatusBadge status={r.run_status} />}
                        {r.run_review_status && <StatusBadge status={r.run_review_status} />}
                        <TextLink href={`/research/${r.research_run_id}`}>Open</TextLink>
                      </span>
                    ) : (
                      <span className="text-fg-3">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </div>
  );
}
