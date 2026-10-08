"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ChangeEvent } from "react";

import { Badge, Card, Empty, ErrorNote, formatDate, Loading } from "@/components/ui";
import { api } from "@/lib/client";
import { useApi } from "@/lib/hooks";
import type { ImportDetail, ImportJob } from "@/lib/types";

const MAX_BYTES = 2_000_000;

export default function DiscoverPage() {
  const router = useRouter();
  const { data: imports, error } = useApi<ImportJob[]>("/discovery/imports");
  const [busy, setBusy] = useState(false);
  const [uploadError, setUploadError] = useState<unknown>(null);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploadError(null);
    if (file.size > MAX_BYTES) {
      setUploadError(new Error("The file is larger than 2 MB. Split it into smaller files."));
      return;
    }
    setBusy(true);
    try {
      const content = await file.text();
      const job = await api<ImportDetail>("/discovery/imports", { method: "POST", body: { filename: file.name, content } });
      router.push(`/discover/${job.id}`);
    } catch (err) {
      setUploadError(err);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Discover</h1>
      <Card title="Import companies from a CSV file">
        <p className="mb-3 text-sm text-muted">
          One company per row, with a header row. A website column is required; name, country, industry and notes are optional.
          Nothing is added to Accounts: you choose which rows to research, then approve or reject each one as usual.
        </p>
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-md bg-foreground px-3 py-1.5 text-sm font-medium text-background">
          <input type="file" accept=".csv,text/csv,text/plain" onChange={upload} disabled={busy} className="sr-only" aria-label="CSV file" />
          {busy ? "Uploading…" : "Choose CSV file"}
        </label>
        <div className="mt-3"><ErrorNote error={uploadError} /></div>
      </Card>
      <Card title="Import history">
        {error && <ErrorNote error={error} />}
        {!imports && !error && <Loading />}
        {imports?.length === 0 && <Empty>No imports yet.</Empty>}
        {imports && imports.length > 0 && (
          <ul className="divide-y divide-border text-sm" data-testid="imports">
            {imports.map((job) => (
              <li key={job.id} className="flex flex-wrap items-center gap-2 py-2">
                <Link href={`/discover/${job.id}`} className="font-medium hover:underline">{job.name}</Link>
                <span className="text-muted">{job.row_count} rows · {formatDate(job.created_at, true)}</span>
                {job.status === "uploaded" ? <Badge tone="amber">Columns not mapped</Badge> : (
                  <span className="flex gap-1">
                    {job.stats.new ? <Badge tone="green">{job.stats.new} new</Badge> : null}
                    {job.stats.queued ? <Badge tone="blue">{job.stats.queued} researching</Badge> : null}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
