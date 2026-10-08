"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ChangeEvent, type FormEvent } from "react";

import { Badge, Button, Card, Empty, ErrorNote, formatDate, inputClass, Loading } from "@/components/ui";
import { api } from "@/lib/client";
import { useApi } from "@/lib/hooks";
import type { ImportDetail, ImportJob } from "@/lib/types";

const MAX_BYTES = 2_000_000;

type ProviderStatus = { name: string; status: "ok" | "degraded" | "off"; detail: string };

function WebSearch() {
  const router = useRouter();
  const { data: providers } = useApi<ProviderStatus[]>("/system/providers");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const search = providers?.find((p) => p.name === "Web search");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const job = await api<ImportDetail>("/discovery/searches", {
        method: "POST",
        body: { query: String(data.get("query") ?? "").trim(), pages: Number(data.get("pages") ?? 1) },
      });
      router.push(`/discover/${job.id}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  if (!search) return null;
  if (search.status !== "ok") {
    return (
      <Card title="Search the web">
        <p className="text-sm text-muted">Web search is not set up on this server. {search.detail}</p>
      </Card>
    );
  }
  return (
    <Card title="Search the web">
      <p className="mb-3 text-sm text-muted">
        Describe the companies you want, e.g. &ldquo;immigration advisers in Manchester&rdquo;. Company websites from the
        results are checked against your accounts and the do-not-contact list; directories and social networks are left out.
      </p>
      <form onSubmit={submit} className="flex flex-wrap gap-2">
        <input name="query" required minLength={3} maxLength={200} aria-label="Search query" placeholder="What kind of companies?" className={`${inputClass} min-w-64 flex-1`} />
        <select name="pages" defaultValue="1" aria-label="Result pages" className={`${inputClass} w-auto`}>
          <option value="1">1 page of results</option>
          <option value="2">2 pages</option>
          <option value="3">3 pages</option>
        </select>
        <Button type="submit" busy={busy}>Search</Button>
      </form>
      <div className="mt-3"><ErrorNote error={error} /></div>
    </Card>
  );
}

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
      <WebSearch />
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
      <Card title="History">
        {error && <ErrorNote error={error} />}
        {!imports && !error && <Loading />}
        {imports?.length === 0 && <Empty>No imports yet.</Empty>}
        {imports && imports.length > 0 && (
          <ul className="divide-y divide-border text-sm" data-testid="imports">
            {imports.map((job) => (
              <li key={job.id} className="flex flex-wrap items-center gap-2 py-2">
                <Badge>{job.kind === "search" ? "Search" : "CSV"}</Badge>
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
