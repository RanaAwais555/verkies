"use client";

import { CircleSlash, Search, Sparkles } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { LeadCard } from "@/components/leads/lead-card";
import { Button, Empty, ErrorNote, inputClass, PageHeader, Panel, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { LeadSearch, RankedLead } from "@/lib/types";

// The master context's own examples (§15), so people see what kind of request works.
const EXAMPLES = [
  "Find 20 companies Verkies should contact this week",
  "London law firms that could benefit from CRM and client portals",
  "UK companies hiring developers within the last 6 months",
  "Companies with strong SEO opportunity but weak conversion",
];

function Results({ leads }: { leads: RankedLead[] }) {
  if (leads.length === 0) {
    return (
      <Panel>
        <Empty icon={<CircleSlash className="h-4 w-4" />}>
          No account matches. Nothing is made up to fill the list: research or import more companies to widen it.
        </Empty>
      </Panel>
    );
  }
  return (
    <div className="space-y-3" data-testid="leads">
      {leads.map((lead) => (
        <LeadCard key={lead.account.id} lead={lead} />
      ))}
    </div>
  );
}

function Interpretation({ search }: { search: LeadSearch }) {
  const { understood, unsupported } = search.interpretation;
  return (
    <Panel title="Read as" description="Every part of your request and what it was used for." testId="interpretation">
      {understood.length === 0 ? (
        <p className="text-[13px] text-fg-3">Nothing in the request could be used as a filter, so this is the full ranked list.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {understood.map((u, i) => (
            <li key={i} className="rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-[12.5px]">
              <span className="font-medium text-fg">{u.phrase}</span>
              <span className="text-fg-3"> → {u.meaning}</span>
            </li>
          ))}
        </ul>
      )}
      {unsupported.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {unsupported.map((u, i) => (
            <li key={i} className="rounded-lg border border-warn/30 bg-warn-soft px-3 py-2 text-[12.5px] text-fg">
              <span className="font-medium">“{u.phrase}”</span> was not used. {u.meaning}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export default function TopLeadsPage() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const q = params.get("q")?.trim() ?? "";
  const [draft, setDraft] = useState(q);
  const top = useApi<RankedLead[]>(q ? null : "/leads/top?limit=20");
  const found = useApi<LeadSearch>(q ? `/leads/search?q=${encodeURIComponent(q)}` : null);

  // The request lives in the address, so a search can be shared or reopened from the palette.
  function ask(query: string) {
    const clean = query.trim();
    setDraft(clean);
    router.replace(clean ? `${pathname}?q=${encodeURIComponent(clean)}` : pathname, { scroll: false });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    ask(draft);
  }

  const error = q ? found.error : top.error;
  const leads = q ? found.data?.results : top.data;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Revenue"
        title="Top Leads"
        description="The best available prospects, not the newest. Each one says why it ranks where it does, from its scores, signals and opportunities."
      />
      <Panel title="Ask in plain English" description="Your request becomes filters over what VROS already knows. You see exactly how it was read.">
        <form onSubmit={submit} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
          <span className="relative">
            <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-3" />
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              maxLength={300}
              aria-label="Describe the companies you want"
              placeholder="e.g. London law firms that could use a client portal"
              className={`${inputClass} pl-8`}
            />
          </span>
          <Button type="submit" variant="primary" icon={<Sparkles className="h-4 w-4" />}>
            Find leads
          </Button>
        </form>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-fg-3">Try:</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => ask(example)}
              className="rounded-full border border-border bg-surface-2 px-3 py-1 text-xs text-fg-2 transition-colors hover:border-accent/50 hover:text-fg"
            >
              {example}
            </button>
          ))}
          {q && (
            <button type="button" onClick={() => ask("")} className="text-xs text-fg-3 underline-offset-2 hover:text-fg hover:underline">
              Clear and show the top 20
            </button>
          )}
        </div>
      </Panel>

      {q && found.data && <Interpretation search={found.data} />}
      {error && <ErrorNote error={error} />}
      {!leads && !error && <Skeleton rows={6} />}
      {leads && <Results leads={leads} />}
    </div>
  );
}
