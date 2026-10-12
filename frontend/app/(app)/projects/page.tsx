"use client";

import { FolderKanban } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { ProjectTable } from "@/components/clients/projects";
import { Checkbox, Empty, ErrorNote, PageHeader, Panel, Skeleton, Tabs } from "@/components/ui";
import { useApi, useTab } from "@/lib/hooks";
import type { Project } from "@/lib/types";

const DESCRIPTIONS: Record<string, string> = {
  open: "Not yet completed or cancelled, soonest target first.",
  closed: "Completed and cancelled projects.",
  all: "Every project.",
};

export default function ProjectsPage() {
  const [tab, setTab] = useTab("open");
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const mine = params.get("mine") === "1";
  const { data, error } = useApi<Project[]>(`/projects?status=${tab}${mine ? "&mine=true" : ""}`);

  function setMine(on: boolean) {
    const next = new URLSearchParams(params);
    if (on) next.set("mine", "1");
    else next.delete("mine");
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Clients"
        title="Projects"
        description="Work for clients after a deal is won: who owns it, its milestones, and anything overdue or at risk. A project starts when a won deal is converted to a client."
      />
      <Tabs
        label="Which projects"
        tabs={[
          { key: "open", label: "In progress" },
          { key: "closed", label: "Finished" },
          { key: "all", label: "All" },
        ]}
        active={tab}
        onChange={setTab}
      />
      <Panel
        title="Projects"
        description={DESCRIPTIONS[tab]}
        actions={<Checkbox label="Only mine" checked={mine} onChange={(e) => setMine(e.target.checked)} />}
      >
        {error ? (
          <ErrorNote error={error} />
        ) : !data ? (
          <Skeleton rows={5} />
        ) : data.length === 0 ? (
          <Empty icon={<FolderKanban className="h-4 w-4" />}>
            {tab === "open" ? "No projects in progress. Convert a won deal to a client from the pipeline to start one." : "No projects here."}
          </Empty>
        ) : (
          <ProjectTable projects={data} />
        )}
      </Panel>
    </div>
  );
}
