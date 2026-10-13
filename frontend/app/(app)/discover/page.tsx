"use client";

import { Building2, FileUp, Globe2, Landmark, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ChangeEvent, type FormEvent, type ReactNode, useState } from "react";

import { Badge, Button, Checkbox, controlClass, Empty, ErrorNote, Field, inputClass, PageHeader, Panel, Skeleton, Spinner } from "@/components/ui";
import { api } from "@/lib/client";
import { formatDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { ImportDetail, ImportJob, ProviderStatus, RegisterOptions } from "@/lib/types";

const MAX_BYTES = 2_000_000;

// Common UK SIC codes for Verkies' ICP; any 5-digit code works.
const SIC_HINTS = "69102 solicitors, 69109 other legal, 70229 consultancy, 62012 software, 86900 health, 85590 education, 68310 estate agents";

const KIND: Record<string, { label: string; tone: "blue" | "purple" | "neutral" }> = {
  search: { label: "Web search", tone: "blue" },
  registry: { label: "Companies House", tone: "purple" },
  register: { label: "Register", tone: "purple" },
};

// Specialists list few areas of work; generalists list many.
const SPECIALIST_MAX_AREAS = 3;

/** A source's heading: an icon tile, a title and one plain sentence on what it does. */
function SourceHead({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="mb-4 flex gap-3">
      <span aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-accent-soft text-accent-text">
        {icon}
      </span>
      <div className="min-w-0 space-y-0.5">
        <h2 className="text-[14px] font-semibold text-fg">{title}</h2>
        <p className="text-[13px] leading-relaxed text-fg-2">{children}</p>
      </div>
    </div>
  );
}

function Unavailable({ provider }: { provider: ProviderStatus }) {
  return (
    <p className="rounded-lg border border-dashed border-border-strong px-3 py-2.5 text-[13px] text-fg-3">
      Not set up on this server. {provider.detail}
    </p>
  );
}

function WebSearch({ provider }: { provider: ProviderStatus }) {
  const router = useRouter();
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const job = await run(() =>
      api<ImportDetail>("/discovery/searches", {
        method: "POST",
        body: { query: String(data.get("query") ?? "").trim(), pages: Number(data.get("pages") ?? 1) },
      }),
    );
    if (job) router.push(`/discover/${job.id}`);
  }

  return (
    <Panel primary>
      <SourceHead icon={<Globe2 className="h-4 w-4" />} title="Search the web">
        Describe the companies you want, e.g. &ldquo;immigration advisers in Manchester&rdquo;. Websites found are checked against your accounts
        and the do-not-contact list; directories and social networks are left out.
      </SourceHead>
      {provider.status !== "ok" ? (
        <Unavailable provider={provider} />
      ) : (
        <form onSubmit={submit} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
          <span className="relative">
            <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-3" />
            <input name="query" required minLength={3} maxLength={200} aria-label="Search query" placeholder="What kind of companies?" className={`${inputClass} pl-8`} />
          </span>
          <select name="pages" defaultValue="1" aria-label="Result pages" className={controlClass}>
            <option value="1">1 page of results</option>
            <option value="2">2 pages</option>
            <option value="3">3 pages</option>
          </select>
          <Button type="submit" variant="primary" busy={busy}>
            Search
          </Button>
        </form>
      )}
      <div className="mt-3">
        <ErrorNote error={error} />
      </div>
    </Panel>
  );
}

function RegistrySearch({ provider }: { provider: ProviderStatus }) {
  const router = useRouter();
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const codes = String(data.get("sic") ?? "")
      .split(/[\s,]+/)
      .map((c) => c.trim())
      .filter(Boolean);
    const job = await run(() =>
      api<ImportDetail>("/discovery/registry-searches", {
        method: "POST",
        body: {
          sic_codes: codes,
          location: String(data.get("location") ?? "").trim() || null,
          incorporated_to: String(data.get("before") ?? "") || null,
          size: Number(data.get("size") ?? 25),
        },
      }),
    );
    if (job) router.push(`/discover/${job.id}`);
  }

  return (
    <Panel>
      <SourceHead icon={<Building2 className="h-4 w-4" />} title="Find companies on Companies House">
        Active UK companies by industry code (SIC) and location. VROS then looks for each one&apos;s website and keeps a site only if it shows the same
        company number.
      </SourceHead>
      {provider.status !== "ok" ? (
        <Unavailable provider={provider} />
      ) : (
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
          <Field label="SIC codes">
            <input name="sic" required placeholder="69102, 69109" className={inputClass} />
          </Field>
          <Field label="Location">
            <input name="location" placeholder="e.g. Leeds" maxLength={80} className={inputClass} />
          </Field>
          <Field label="Incorporated before (optional)">
            <input name="before" type="date" className={inputClass} />
          </Field>
          <Field label="How many">
            <select name="size" defaultValue="25" className={inputClass}>
              {[10, 25, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </Field>
          <p className="text-xs leading-relaxed text-fg-3 sm:col-span-2 2xl:col-span-4">Common codes: {SIC_HINTS}. Any 5-digit code works.</p>
          <div className="space-y-3 sm:col-span-2 2xl:col-span-4">
            <Button type="submit" busy={busy} icon={<Search className="h-4 w-4" />}>
              Find companies
            </Button>
            <ErrorNote error={error} />
          </div>
        </form>
      )}
    </Panel>
  );
}

/** Slice 8.1: search a regulator's register VROS keeps (the SRA's law firms), by area of work,
 * location, size and how specialised a firm is. Every result has the regulator's own website and
 * company number, so nothing is guessed. */
function RegisterSearch({ provider }: { provider: ProviderStatus }) {
  const router = useRouter();
  const { busy, error, run } = useAction();
  const { data: options, error: optionsError } = useApi<RegisterOptions>(provider.status === "ok" ? "/registers/sra/options" : null);
  const [where, setWhere] = useState("london");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const area = String(data.get("area") ?? "");
    const custom = String(data.get("postcodes") ?? "")
      .toUpperCase()
      .split(/[\s,]+/)
      .filter(Boolean);
    const number = (name: string) => (data.get(name) ? Number(data.get(name)) : null);
    const job = await run(() =>
      api<ImportDetail>("/discovery/register-searches", {
        method: "POST",
        body: {
          source: "sra",
          areas: area ? [area] : [],
          postcode_areas: where === "london" ? (options?.london_postcode_areas ?? []) : where === "custom" ? custom : [],
          offices_min: number("offices_min"),
          offices_max: number("offices_max"),
          max_areas: data.get("specialists") ? SPECIALIST_MAX_AREAS : null,
          authorised_since: String(data.get("since") ?? "") || null,
          limit: Number(data.get("limit") ?? 100),
        },
      }),
    );
    if (job) router.push(`/discover/${job.id}`);
  }

  return (
    <Panel primary testId="register-search">
      <SourceHead icon={<Landmark className="h-4 w-4" />} title="Search the SRA register of law firms">
        Every firm the Solicitors Regulation Authority regulates, kept in VROS and refreshed daily. Each result comes with the firm&apos;s own website and
        company number from the register.
      </SourceHead>
      {provider.status !== "ok" ? (
        <Unavailable provider={provider} />
      ) : optionsError ? (
        <ErrorNote error={optionsError} />
      ) : !options ? (
        <Skeleton rows={2} />
      ) : !options.loaded ? (
        <p className="rounded-lg border border-dashed border-border-strong px-3 py-2.5 text-[13px] text-fg-3">
          The register has not been loaded yet. It loads with the worker&apos;s next hourly run, or an admin can refresh it now under Settings, System.
        </p>
      ) : (
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
          <Field label="Area of work">
            <select name="area" defaultValue={options.areas.some((a) => a.area === "Immigration") ? "Immigration" : ""} className={inputClass}>
              <option value="">Any area</option>
              {options.areas.map((a) => (
                <option key={a.area} value={a.area}>
                  {a.area} ({a.organisations.toLocaleString()})
                </option>
              ))}
            </select>
          </Field>
          <Field label="Office location">
            <select value={where} onChange={(e) => setWhere(e.target.value)} className={inputClass} aria-label="Office location">
              <option value="london">London</option>
              <option value="anywhere">Anywhere</option>
              <option value="custom">Postcode areas…</option>
            </select>
          </Field>
          {where === "custom" && (
            <Field label="Postcode areas" hint="Letters before the first digit, e.g. M, LS, B">
              <input name="postcodes" required placeholder="M, LS, B" className={inputClass} />
            </Field>
          )}
          <Field label="Offices">
            <span className="flex items-center gap-2">
              <input name="offices_min" type="number" min={1} max={1000} placeholder="Min" aria-label="Fewest offices" className={inputClass} />
              <input name="offices_max" type="number" min={1} max={1000} placeholder="Max" aria-label="Most offices" className={inputClass} />
            </span>
          </Field>
          <Field label="Authorised since (optional)">
            <input name="since" type="date" className={inputClass} />
          </Field>
          <Field label="How many">
            <select name="limit" defaultValue="100" className={inputClass}>
              {[50, 100, 250, 500].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </Field>
          <Checkbox
            name="specialists"
            label={`Specialists only (at most ${SPECIALIST_MAX_AREAS} areas of work)`}
            className="self-end pb-2 sm:col-span-2"
          />
          <div className="space-y-3 sm:col-span-2 2xl:col-span-4">
            <Button type="submit" busy={busy} icon={<Search className="h-4 w-4" />}>
              Search the register
            </Button>
            <ErrorNote error={error} />
            <p className="text-xs leading-relaxed text-fg-3">{options.attribution}</p>
          </div>
        </form>
      )}
    </Panel>
  );
}

function CsvImport() {
  const router = useRouter();
  const { busy, error, setError, run } = useAction();

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError(new Error("The file is larger than 2 MB. Split it into smaller files."));
      return;
    }
    const job = await run(async () => api<ImportDetail>("/discovery/imports", { method: "POST", body: { filename: file.name, content: await file.text() } }));
    if (job) router.push(`/discover/${job.id}`);
  }

  return (
    <Panel>
      <SourceHead icon={<FileUp className="h-4 w-4" />} title="Import a CSV file">
        One company per row, with a header row. A website column is required; name, country, industry and notes are optional. You choose which rows to
        research.
      </SourceHead>
      <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-[9px] border border-border-strong bg-surface-2 px-3.5 text-[13px] font-medium text-fg transition-colors hover:border-accent/60 focus-within:ring-2 focus-within:ring-accent/50">
        <input type="file" accept=".csv,text/csv,text/plain" onChange={upload} disabled={busy} className="sr-only" aria-label="CSV file" />
        {busy ? <Spinner /> : <FileUp aria-hidden className="h-4 w-4" />}
        {busy ? "Uploading…" : "Choose CSV file"}
      </label>
      <span className="ml-3 text-xs text-fg-3">Up to 2 MB</span>
      <div className="mt-3">
        <ErrorNote error={error} />
      </div>
    </Panel>
  );
}

function JobStatus({ job }: { job: ImportJob }) {
  if (job.status === "running") return <Badge tone="blue">Finding websites…</Badge>;
  if (job.status === "uploaded") return <Badge tone="amber">Columns not mapped</Badge>;
  return (
    <span className="flex gap-1">
      {job.stats.new ? <Badge tone="green">{job.stats.new} new</Badge> : null}
      {job.stats.queued ? <Badge tone="blue">{job.stats.queued} researching</Badge> : null}
    </span>
  );
}

export default function DiscoverPage() {
  const { data: providers } = useApi<ProviderStatus[]>("/system/providers");
  const { data: imports, error } = useApi<ImportJob[]>("/discovery/imports");
  const web = providers?.find((p) => p.name === "Web search");
  const registry = providers?.find((p) => p.name === "Companies House");
  const sra = providers?.find((p) => p.name === "SRA register");

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Revenue"
        title="Discover"
        description="Find new companies: search a regulator's register, the web or Companies House, or import a list. Nothing reaches Accounts until you approve it."
      />
      {!providers && <Skeleton rows={3} />}
      {sra && <RegisterSearch provider={sra} />}
      {web && <WebSearch provider={web} />}
      <div className="grid items-start gap-5 lg:grid-cols-2">
        {registry && <RegistrySearch provider={registry} />}
        <CsvImport />
      </div>
      <Panel title="History" collapsible>
        {error && <ErrorNote error={error} />}
        {!imports && !error && <Skeleton rows={4} />}
        {imports?.length === 0 && <Empty>No searches or imports yet.</Empty>}
        {imports && imports.length > 0 && (
          <ul className="divide-y divide-grid" data-testid="imports">
            {imports.map((job) => (
              <li key={job.id} className="flex flex-wrap items-center gap-2 py-2.5 text-[13px] first:pt-0 last:pb-0">
                <Badge tone={KIND[job.kind]?.tone ?? "neutral"}>{KIND[job.kind]?.label ?? "CSV"}</Badge>
                <Link href={`/discover/${job.id}`} className="font-medium text-fg hover:text-accent-text">
                  {job.name}
                </Link>
                <span className="text-fg-3">
                  {job.row_count} rows · {formatDate(job.created_at, true)}
                </span>
                <JobStatus job={job} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
