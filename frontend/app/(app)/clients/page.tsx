"use client";

import { RefreshCw } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { ClientTable, NoClients } from "@/components/clients/health";
import { Button, Checkbox, ErrorNote, PageHeader, Panel, Skeleton, Success, Tabs } from "@/components/ui";
import { api } from "@/lib/client";
import { can, useAction, useApi, useSession } from "@/lib/hooks";
import type { ClientSummary } from "@/lib/types";

const FILTERS = [
  { key: "all", label: "All clients" },
  { key: "red", label: "Red" },
  { key: "yellow", label: "Yellow" },
  { key: "green", label: "Green" },
  { key: "expansion", label: "Expansion potential" },
];

export default function ClientsPage() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { data: session } = useSession();
  const health = params.get("health") ?? "all";
  const expansion = params.get("expansion") === "1";
  const mine = params.get("mine") === "1";
  const query = new URLSearchParams();
  if (health !== "all") query.set("health", health);
  if (mine) query.set("mine", "true");
  if (expansion) query.set("expansion", "true");
  const { data, error } = useApi<ClientSummary[]>(`/clients${query.size ? `?${query}` : ""}`);
  const { busy, error: checkError, run } = useAction();
  const [checked, setChecked] = useState<string | null>(null);

  function setParam(key: string, value: string | null, clear?: string) {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    if (clear) next.delete(clear);
    const q = next.toString();
    router.replace(q ? `${pathname}?${q}` : pathname, { scroll: false });
  }

  async function checkNow() {
    setChecked(null);
    const done = await run(() => api<{ assessed: number; changed: number; risks_raised: number }>("/clients/health-check", { method: "POST" }));
    if (done)
      setChecked(
        `Checked ${done.assessed} client${done.assessed === 1 ? "" : "s"}: ${done.changed} changed colour, ${done.risks_raised} new risk${done.risks_raised === 1 ? "" : "s"} raised.`,
      );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Clients"
        title="Client health"
        description="Every client, Green, Yellow or Red, from their projects, milestones, risks, tasks, how recently anyone spoke to them, and what they said. Worst first."
        actions={
          can(session, "reports.team") && (
            <Button onClick={checkNow} busy={busy} icon={<RefreshCw className="h-4 w-4" />}>
              Check now
            </Button>
          )
        }
      />
      {checked && <Success>{checked}</Success>}
      <ErrorNote error={checkError} />
      <Tabs
        label="Filter by health"
        tabs={FILTERS}
        active={expansion ? "expansion" : health}
        onChange={(key) => (key === "expansion" ? setParam("expansion", "1", "health") : setParam("health", key === "all" ? null : key, "expansion"))}
      />
      <Panel
        title="Clients"
        description="Health is worked out on every visit. Each morning VROS records any change and gives the account manager a task when a client turns Red."
        actions={<Checkbox label="Only mine" checked={mine} onChange={(e) => setParam("mine", e.target.checked ? "1" : null)} />}
      >
        {error ? <ErrorNote error={error} /> : !data ? <Skeleton rows={5} /> : data.length === 0 ? <NoClients /> : <ClientTable clients={data} />}
      </Panel>
    </div>
  );
}
