"use client";

import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Badge, Button, Card, ErrorNote, Field, inputClass, label, Loading, StatusBadge, TextLink } from "@/components/ui";
import { api } from "@/lib/client";
import { useApi } from "@/lib/hooks";
import type { ImportDetail, ImportRow } from "@/lib/types";

const MAX_PER_BATCH = 50;
const RESEARCHABLE = new Set(["new", "possible_duplicate"]);
const STATUS_TONE: Record<ImportRow["status"], "green" | "amber" | "red" | "purple" | "blue" | "neutral"> = {
  pending: "neutral",
  new: "green",
  invalid: "red",
  duplicate_in_file: "neutral",
  existing_account: "purple",
  possible_duplicate: "amber",
  already_researched: "neutral",
  suppressed: "red",
  queued: "blue",
};

function Mapping({ job, onChecked }: { job: ImportDetail; onChecked: (job: ImportDetail) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const mapping = Object.fromEntries(job.fields.map((f) => [f, String(data.get(f) ?? "")]));
    setBusy(true);
    setError(null);
    try {
      onChecked(await api<ImportDetail>(`/discovery/imports/${job.id}/mapping`, { method: "PUT", body: { mapping } }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Which column is which?">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {job.fields.map((field) => (
            <Field key={field} label={field === "website" ? "Website (required)" : label(field)}>
              <select name={field} defaultValue={job.mapping[field] ?? ""} className={inputClass}>
                <option value="">Not in this file</option>
                {job.columns.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
          ))}
        </div>
        <ErrorNote error={error} />
        <Button type="submit" busy={busy}>{job.status === "checked" ? "Check again" : "Check rows"}</Button>
      </form>
    </Card>
  );
}

export default function ImportPage() {
  const { id } = useParams<{ id: string }>();
  const { data: job, error, mutate } = useApi<ImportDetail>(`/discovery/imports/${id}`, {
    refreshInterval: (latest) => (latest?.rows.some((r) => r.run_status && ["queued", "running", "retrying"].includes(r.run_status)) ? 5000 : 0),
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [result, setResult] = useState<string | null>(null);

  if (error) return <ErrorNote error={error} />;
  if (!job) return <Loading />;

  const researchable = job.rows.filter((r) => RESEARCHABLE.has(r.status));
  const toggle = (rowId: string) => {
    const next = new Set(selected);
    if (next.has(rowId)) next.delete(rowId);
    else if (next.size < MAX_PER_BATCH) next.add(rowId);
    setSelected(next);
  };

  async function research() {
    setBusy(true);
    setActionError(null);
    setResult(null);
    try {
      const out = await api<{ started: string[]; skipped: Record<string, string>; queue_failures: number }>(
        `/discovery/imports/${id}/research`,
        { method: "POST", body: { row_ids: [...selected] } },
      );
      const skipped = Object.keys(out.skipped).length;
      setResult(`Started research on ${out.started.length} compan${out.started.length === 1 ? "y" : "ies"}${skipped ? `; ${skipped} skipped` : ""}${out.queue_failures ? `; ${out.queue_failures} could not be queued` : ""}.`);
      setSelected(new Set());
      await mutate();
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{job.name}</h1>
        <span className="text-sm text-muted">{job.row_count} rows</span>
      </div>
      <Mapping job={job} onChecked={(checked) => { setSelected(new Set()); mutate(checked, { revalidate: false }); }} />
      {job.status === "checked" && (
        <Card
          title="Rows"
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" onClick={() => setSelected(new Set(researchable.filter((r) => r.status === "new").slice(0, MAX_PER_BATCH).map((r) => r.id)))}>
                Select new ({Math.min(MAX_PER_BATCH, researchable.filter((r) => r.status === "new").length)})
              </Button>
              <Button onClick={research} busy={busy} disabled={selected.size === 0}>Research selected ({selected.size})</Button>
            </div>
          }
        >
          <div className="mb-3 flex flex-wrap gap-1">
            {Object.entries(job.stats).map(([s, n]) => <Badge key={s} tone={STATUS_TONE[s as ImportRow["status"]]}>{n} {label(s).toLowerCase()}</Badge>)}
          </div>
          <ErrorNote error={actionError} />
          {result && <p className="mb-2 text-sm text-green-700" data-testid="research-result">{result}</p>}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="import-rows">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="w-8 py-1" />
                  <th className="py-1 pr-3 font-medium">Row</th>
                  <th className="py-1 pr-3 font-medium">Company</th>
                  <th className="py-1 pr-3 font-medium">Website</th>
                  <th className="py-1 pr-3 font-medium">Check</th>
                  <th className="py-1 pr-3 font-medium">Research</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {job.rows.map((r) => (
                  <tr key={r.id}>
                    <td className="py-1.5">
                      {RESEARCHABLE.has(r.status) && (
                        <input type="checkbox" aria-label={`Select row ${r.row_number}`} checked={selected.has(r.id)} onChange={() => toggle(r.id)} />
                      )}
                    </td>
                    <td className="py-1.5 pr-3 tabular-nums text-muted">{r.row_number}</td>
                    <td className="py-1.5 pr-3">{r.name ?? "—"}{r.industry && <span className="text-xs text-muted"> · {r.industry}</span>}</td>
                    <td className="py-1.5 pr-3">{r.normalised_domain ?? r.website_url ?? "—"}</td>
                    <td className="py-1.5 pr-3">
                      <Badge tone={STATUS_TONE[r.status]}>{label(r.status)}</Badge>
                      {r.status_detail && <div className="text-xs text-muted">{r.status_detail}</div>}
                      {r.matched_account_id && <TextLink href={`/accounts/${r.matched_account_id}`}>Account</TextLink>}
                    </td>
                    <td className="py-1.5 pr-3">
                      {r.research_run_id ? (
                        <span className="flex items-center gap-1">
                          {r.run_status && <StatusBadge status={r.run_status} />}
                          {r.run_review_status && <StatusBadge status={r.run_review_status} />}
                          <TextLink href={`/research/${r.research_run_id}`}>Open</TextLink>
                        </span>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
