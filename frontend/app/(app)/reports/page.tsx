"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { FigureGrid, Funnel, ReportTableCard } from "@/components/reports/report";
import { controlClass, ErrorNote, Note, PageHeader, Skeleton, Tabs } from "@/components/ui";
import { SaveViewButton } from "@/components/views/save-view";
import { formatDate } from "@/lib/format";
import { can, useApi, useSession, useTab } from "@/lib/hooks";
import type { Dashboard, ReportPeriod } from "@/lib/types";

const PERIODS: { key: ReportPeriod; label: string }[] = [
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
  { key: "90d", label: "Last 90 days" },
  { key: "365d", label: "Last 12 months" },
  { key: "ytd", label: "Year to date" },
];

const DASHBOARDS = [
  { key: "sales", label: "Sales", path: "/reports/sales", needs: ["accounts.read", "accounts.read_own"] },
  { key: "intelligence", label: "Lead intelligence", path: "/reports/lead-intelligence", needs: ["accounts.read", "prospects.review"] },
  { key: "management", label: "Management", path: "/reports/management", needs: ["reports.team"] },
];

function Board({ path }: { path: string }) {
  const { data, error } = useApi<Dashboard>(path);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={8} />;
  const tables = data.tables;
  return (
    <div className="space-y-4" data-testid="dashboard">
      <p className="text-xs text-fg-3">
        {formatDate(data.start)} to {formatDate(data.end)}. Every figure is counted from the records as they are now; open &ldquo;How it&apos;s counted&rdquo; for the rule.
      </p>
      <FigureGrid figures={data.figures} />
      {data.funnel && <Funnel steps={data.funnel} />}
      <div className="grid items-start gap-4 lg:grid-cols-2">
        {tables.map((t) => (
          <div key={t.key} className={t.columns.length > 3 ? "min-w-0 lg:col-span-2" : "min-w-0"}>
            <ReportTableCard table={t} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ReportsPage() {
  const { data: session } = useSession();
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const available = DASHBOARDS.filter((d) => can(session, ...d.needs));
  const [tab, setTab] = useTab("sales");
  const active = available.find((d) => d.key === tab) ?? available[0];
  const period = (PERIODS.find((p) => p.key === params.get("period"))?.key ?? "90d") as ReportPeriod;
  const mine = params.get("mine") === "true";

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  const query = new URLSearchParams({ period, ...(active?.key === "sales" && mine ? { mine: "true" } : {}) });
  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Revenue"
        title="Reports"
        description="Sales, lead intelligence and management dashboards, counted from VROS's own records. Nothing is estimated: a figure with nothing to measure shows Unknown."
        actions={
          <>
            {active?.key === "sales" && (
              <select value={mine ? "mine" : "all"} onChange={(e) => setParam("mine", e.target.value === "mine" ? "true" : null)} aria-label="Whose work" className={`${controlClass} w-40`}>
                <option value="all">Everyone I can see</option>
                <option value="mine">Only mine</option>
              </select>
            )}
            <select value={period} onChange={(e) => setParam("period", e.target.value)} aria-label="Period" className={`${controlClass} w-40`}>
              {PERIODS.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label}
                </option>
              ))}
            </select>
            <SaveViewButton suggestedName={active ? `${active.label} report` : ""} />
          </>
        }
      />
      {session && available.length === 0 && <Note>Your role has no reports.</Note>}
      {active && (
        <>
          {available.length > 1 && <Tabs label="Dashboards" tabs={available.map((d) => ({ key: d.key, label: d.label }))} active={active.key} onChange={setTab} />}
          <Board key={`${active.key}${query}`} path={`${active.path}?${query}`} />
        </>
      )}
    </div>
  );
}
