"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ChangeEvent, type FormEvent } from "react";

import { Badge, Button, Card, Empty, ErrorNote, Field, formatDate, inputClass, Loading } from "@/components/ui";
import { api } from "@/lib/client";
import { useApi } from "@/lib/hooks";
import type { ImportDetail, ImportJob } from "@/lib/types";

const MAX_BYTES = 2_000_000;

type ProviderStatus = { name: string; status: "ok" | "degraded" | "off"; detail: string };

// Common UK SIC codes for Verkies' ICP; any 5-digit code works.
const SIC_HINTS = "69102 solicitors, 69109 other legal, 70229 consultancy, 62012 software, 86900 health, 85590 education, 68310 estate agents";

function RegistrySearch() {
  const router = useRouter();
  const { data: providers } = useApi<ProviderStatus[]>("/system/providers");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const registry = providers?.find((p) => p.name === "Companies House");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const codes = String(data.get("sic") ?? "").split(/[\s,]+/).map((c) => c.trim()).filter(Boolean);
    setBusy(true);
    setError(null);
    try {
      const job = await api<ImportDetail>("/discovery/registry-searches", {
        method: "POST",
        body: {
          sic_codes: codes,
          location: String(data.get("location") ?? "").trim() || null,
          incorporated_to: String(data.get("before") ?? "") || null,
          size: Number(data.get("size") ?? 25),
        },
      });
      router.push(`/discover/${job.id}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  if (!registry) return null;
  if (registry.status !== "ok") {
    return (
      <Card title="Find companies on Companies House">
        <p className="text-sm text-muted">{registry.detail}</p>
      </Card>
    );
  }
  return (
    <Card title="Find companies on Companies House">
      <p className="mb-3 text-sm text-muted">
        Active UK companies by industry code (SIC) and location. VROS then looks for each one&apos;s website and keeps a site only
        if it shows the same company number.
      </p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4">
        <Field label="SIC codes" hint={SIC_HINTS}>
          <input name="sic" required placeholder="69102, 69109" className={inputClass} />
        </Field>
        <Field label="Location">
          <input name="location" placeholder="e.g. Leeds" maxLength={80} className={inputClass} />
        </Field>
        <Field label="Incorporated before" hint="Optional, e.g. 3+ years ago">
          <input name="before" type="date" className={inputClass} />
        </Field>
        <Field label="How many">
          <select name="size" defaultValue="25" className={inputClass}>
            {[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Field>
        <div className="sm:col-span-4">
          <Button type="submit" busy={busy}>Find companies</Button>
          <div className="mt-3"><ErrorNote error={error} /></div>
        </div>
      </form>
    </Card>
  );
}

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
      <RegistrySearch />
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
                <Badge>{job.kind === "search" ? "Search" : job.kind === "registry" ? "Companies House" : "CSV"}</Badge>
                <Link href={`/discover/${job.id}`} className="font-medium hover:underline">{job.name}</Link>
                <span className="text-muted">{job.row_count} rows · {formatDate(job.created_at, true)}</span>
                {job.status === "running" ? <Badge tone="blue">Finding websites…</Badge> : job.status === "uploaded" ? <Badge tone="amber">Columns not mapped</Badge> : (
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
