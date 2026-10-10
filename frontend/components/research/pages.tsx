import { Badge, Panel, SourceLink } from "@/components/ui";
import type { RunDetail } from "@/lib/types";

/** The pages the crawl fetched, skipped or failed on, with the reason. */
export function PagesView({ run }: { run: RunDetail }) {
  return (
    <Panel title={`Pages (${run.pages.length})`}>
      <ul className="divide-y divide-grid">
        {run.pages.map((p) => (
          <li key={`${p.kind}-${p.url}`} className="flex flex-wrap items-center gap-2 py-2 first:pt-0 last:pb-0">
            <Badge>{p.kind === "page" ? (p.category ?? "page") : p.kind}</Badge>
            <SourceLink url={p.url} />
            <span className="text-xs text-fg-3">
              {p.status_code ?? "—"}
              {p.rendered ? " · rendered" : ""}
              {p.from_cache ? " · cached" : ""}
              {p.skip_reason ? ` · skipped: ${p.skip_reason}` : ""}
              {p.error ? ` · ${p.error}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
