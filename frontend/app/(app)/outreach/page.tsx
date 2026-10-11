"use client";

import { OutreachQueueView } from "@/components/outreach/queue";
import { Sequences, Templates } from "@/components/outreach/library";
import { PageHeader, Tabs } from "@/components/ui";
import { useTab } from "@/lib/hooks";

export default function OutreachPage() {
  const [tab, setTab] = useTab("queue");
  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Revenue"
        title="Outreach"
        description="Your sequences' steps that are due, best prospects first. Nothing is sent by itself: you send each email, send each LinkedIn note in your own browser, and make each call."
      />
      <Tabs
        label="Outreach sections"
        tabs={[
          { key: "queue", label: "Today" },
          { key: "sequences", label: "Sequences" },
          { key: "templates", label: "Templates" },
        ]}
        active={tab}
        onChange={setTab}
      />
      {tab === "queue" && <OutreachQueueView />}
      {tab === "sequences" && <Sequences />}
      {tab === "templates" && <Templates />}
    </div>
  );
}
