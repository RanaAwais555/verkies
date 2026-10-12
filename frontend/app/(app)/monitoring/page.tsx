"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { AlertList, WatchedTable } from "@/components/monitoring/monitoring";
import { Checkbox, PageHeader, Panel, Tabs } from "@/components/ui";

export default function MonitoringPage() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const everyone = params.get("everyone") === "1";
  const show = params.get("show") ?? "open";

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    const q = next.toString();
    router.replace(q ? `${pathname}?${q}` : pathname, { scroll: false });
  }

  const query = new URLSearchParams();
  if (show === "open") query.set("open", "true");
  if (!everyone) query.set("mine", "true");

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Monitoring"
        title="Monitoring"
        description="Watched accounts are re-checked every morning from their own sources: the job boards and news feeds their site links to, and Companies House. Anything new shows here, with where it was found."
      />
      <Panel
        title="Alerts"
        actions={<Checkbox label="Accounts others watch too" checked={everyone} onChange={(e) => setParam("everyone", e.target.checked ? "1" : null)} />}
        testId="alerts"
      >
        <div className="space-y-4">
          <Tabs
            label="Which alerts"
            tabs={[
              { key: "open", label: "To review" },
              { key: "all", label: "All" },
            ]}
            active={show}
            onChange={(key) => setParam("show", key === "open" ? null : key)}
          />
          <AlertList query={query.toString()} empty={show === "open" ? "Nothing new to review." : "No alerts yet."} />
        </div>
      </Panel>
      <Panel title={everyone ? "Every watched account" : "Accounts you watch"} testId="watched-panel">
        <WatchedTable mine={!everyone} />
      </Panel>
    </div>
  );
}
