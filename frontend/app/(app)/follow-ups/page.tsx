"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { FLAG_GROUPS, FollowUpsPanel } from "@/components/crm/follow-ups";
import { PageHeader, Tabs } from "@/components/ui";
import { SaveViewButton } from "@/components/views/save-view";
import type { FollowUpKind } from "@/lib/types";

/** Every follow-up flag, or one kind of them; the kind and "mine" live in the address, so a saved view can open it. */
export default function FollowUpsPage() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const kind = FLAG_GROUPS.find((g) => g.kind === params.get("kind"))?.kind ?? null;
  const mine = params.get("mine") === "true";

  function set(key: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  const title = kind ? FLAG_GROUPS.find((g) => g.kind === kind)!.title : "Follow-ups";
  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Workspace"
        title={title}
        description="The follow-up engine's flags, worked out from tasks, logged activity and stage moves each time you open this page."
        actions={<SaveViewButton suggestedName={title} />}
      />
      <Tabs
        label="Kind of follow-up"
        tabs={[{ key: "all", label: "All" }, ...FLAG_GROUPS.map((g) => ({ key: g.kind, label: g.title }))]}
        active={kind ?? "all"}
        onChange={(key) => set("kind", key === "all" ? null : key)}
      />
      <FollowUpsPanel
        key={kind ?? "all"}
        kinds={kind ? [kind as FollowUpKind] : undefined}
        mine={mine}
        onMine={(value) => set("mine", value ? "true" : null)}
        perGroup={50}
      />
    </div>
  );
}
