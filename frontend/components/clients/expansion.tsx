"use client";

import { Sprout } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Badge, Button, Empty, ErrorNote, Field, inputClass, Panel, Skeleton, SourceLink, Success } from "@/components/ui";
import { api } from "@/lib/client";
import { formatDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { ExpansionSuggestion } from "@/lib/types";

function SuggestionItem({ accountId, suggestion, onDone }: { accountId: string; suggestion: ExpansionSuggestion; onDone: (message: string) => void }) {
  const { busy, error, run } = useAction();
  const [dismissing, setDismissing] = useState(false);
  const [service, setService] = useState(suggestion.services.length === 1 ? suggestion.services[0].id : "");
  const base = `/accounts/${accountId}/expansion/${suggestion.candidate_id}`;

  async function open() {
    const done = await run(() => api(`${base}/open`, { method: "POST", body: { service_id: service || null } }).then(() => true));
    if (done) onDone(`${suggestion.category_name} is now an opportunity on the Overview. Open a deal from it to work it in the expansion pipeline.`);
  }

  async function dismiss(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
    const done = await run(() => api(`${base}/dismiss`, { method: "POST", body: { reason } }).then(() => true));
    if (done) onDone(`${suggestion.category_name} dismissed. It comes back only if new research finds it again.`);
  }

  return (
    <li className="space-y-2.5 py-3.5 first:pt-0 last:pb-0" data-testid="expansion-suggestion">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13.5px] font-semibold text-fg">{suggestion.category_name}</span>
        <Badge tone="accent">{Math.round(suggestion.confidence * 100)}% confidence</Badge>
        {suggestion.dismissed_before && <Badge tone="amber">Found again after being dismissed</Badge>}
      </div>
      <p className="text-[13px] text-fg-2">{suggestion.problem}</p>
      <div className="space-y-1">
        <p className="text-xs font-medium text-fg-3">Evidence, found {formatDate(suggestion.found_at)}</p>
        <ul className="space-y-1.5">
          {suggestion.evidence.map((e) => (
            <li key={e.id} className="rounded-lg bg-sunken px-2.5 py-1.5 text-xs text-fg-2">
              <q className="block">{e.evidence_text}</q>
              <SourceLink url={e.source_url} />
            </li>
          ))}
        </ul>
      </div>
      {dismissing ? (
        <form onSubmit={dismiss} className="flex flex-wrap items-end gap-2">
          <Field label="Why it does not fit" className="min-w-0 flex-1">
            <input name="reason" required minLength={3} maxLength={500} className={inputClass} />
          </Field>
          <Button type="submit" busy={busy}>
            Dismiss
          </Button>
          <Button variant="ghost" onClick={() => setDismissing(false)}>
            Cancel
          </Button>
        </form>
      ) : (
        <div className="flex flex-wrap items-end gap-2">
          {suggestion.services.length > 1 && (
            <Field label="Service">
              <select value={service} onChange={(e) => setService(e.target.value)} className={inputClass}>
                <option value="">Decide later</option>
                {suggestion.services.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {suggestion.services.length === 1 && <p className="pb-2 text-xs text-fg-3">Service: {suggestion.services[0].name}</p>}
          <Button variant="primary" busy={busy} icon={<Sprout className="h-4 w-4" />} onClick={open}>
            Open as an opportunity
          </Button>
          <Button variant="ghost" onClick={() => setDismissing(true)}>
            Dismiss
          </Button>
        </div>
      )}
      <ErrorNote error={error} />
    </li>
  );
}

/** §14 expansion engine on the account: only problems research found on the client's own site. */
export function ExpansionPanel({ accountId, onChange }: { accountId: string; onChange: () => void }) {
  const { data, error, mutate } = useApi<ExpansionSuggestion[]>(`/accounts/${accountId}/expansion`);
  const [message, setMessage] = useState<string | null>(null);
  return (
    <Panel
      title="Expansion"
      description="Problems research found on this client's own website that they have no opportunity for yet, each with its evidence. Research the website again for fresh findings."
      testId="expansion"
    >
      <div className="space-y-4">
        {message && <Success>{message}</Success>}
        {error ? (
          <ErrorNote error={error} />
        ) : !data ? (
          <Skeleton rows={3} />
        ) : data.length === 0 ? (
          <Empty icon={<Sprout className="h-4 w-4" />}>No expansion suggestions. Nothing research found is waiting for a decision.</Empty>
        ) : (
          <ul className="divide-y divide-grid">
            {data.map((s) => (
              <SuggestionItem
                key={s.candidate_id}
                accountId={accountId}
                suggestion={s}
                onDone={(text) => {
                  setMessage(text);
                  void mutate();
                  onChange();
                }}
              />
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}
