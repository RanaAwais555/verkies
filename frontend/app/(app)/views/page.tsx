"use client";

import { Bookmark, Trash2, Users } from "lucide-react";
import Link from "next/link";

import { Empty, ErrorNote, IconButton, PageHeader, Panel, Skeleton } from "@/components/ui";
import { api } from "@/lib/client";
import { useAction, useApi } from "@/lib/hooks";
import type { SavedView } from "@/lib/types";

const PAGE_NAMES: Record<string, string> = {
  "/leads": "Lead search",
  "/accounts": "Accounts",
  "/pipeline": "Pipeline",
  "/tasks": "Tasks",
  "/follow-ups": "Follow-ups",
  "/reports": "Reports",
  "/discover": "Discover",
  "/duplicates": "Duplicates",
  "/research": "Lead Intelligence",
};

function hrefOf(v: SavedView): string {
  return v.query ? `${v.path}?${v.query}` : v.path;
}

/** What a view filters on, read back from its link: "q: my hot leads", "due: today". */
function describe(v: SavedView): string {
  const page = PAGE_NAMES[v.path] ?? v.path;
  const filters = [...new URLSearchParams(v.query).entries()].map(([k, value]) => (k === "q" ? `“${value}”` : `${k.replace("_", " ")}: ${value.replace("_", " ")}`));
  return filters.length ? `${page} · ${filters.join(" · ")}` : page;
}

function ViewList({ views, onChange }: { views: SavedView[]; onChange: () => void }) {
  const { error, run } = useAction();
  return (
    <>
      <ErrorNote error={error} />
      <ul className="divide-y divide-grid" data-testid="saved-views">
        {views.map((v) => (
          <li key={v.id} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
            <Bookmark aria-hidden className="h-4 w-4 shrink-0 text-accent-text" />
            <div className="min-w-0 flex-1">
              <Link href={hrefOf(v)} className="font-medium text-fg hover:text-accent-text hover:underline">
                {v.name}
              </Link>
              <p className="truncate text-xs text-fg-3">{describe(v)}</p>
            </div>
            {v.can_delete && (
              <IconButton
                label={`Remove ${v.name}`}
                onClick={async () => {
                  if (await run(() => api(`/saved-views/${v.id}`, { method: "DELETE" }).then(() => true))) onChange();
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </IconButton>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

export default function SavedViewsPage() {
  const { data, error, mutate } = useApi<SavedView[]>("/saved-views");
  const team = data?.filter((v) => v.shared) ?? [];
  const mine = data?.filter((v) => !v.shared) ?? [];
  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Workspace"
        title="Saved views"
        description="Named links to pages with their filters. Each one shows today's data when you open it. Save your own with “Save view” on a lead search, the pipeline, tasks, follow-ups or a report."
      />
      {error && <ErrorNote error={error} />}
      {!data && !error && <Skeleton rows={6} />}
      {data && (
        <div className="grid items-start gap-4 lg:grid-cols-2">
          <Panel title="Team views" description="Shared with everyone. Managed by people who manage configuration.">
            {team.length === 0 ? <Empty icon={<Users className="h-4 w-4" />}>No team views.</Empty> : <ViewList views={team} onChange={() => mutate()} />}
          </Panel>
          <Panel title="My views" description="Only you see these.">
            {mine.length === 0 ? <Empty icon={<Bookmark className="h-4 w-4" />}>You have not saved a view yet.</Empty> : <ViewList views={mine} onChange={() => mutate()} />}
          </Panel>
        </div>
      )}
    </div>
  );
}
