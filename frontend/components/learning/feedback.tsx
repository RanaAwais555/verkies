"use client";

import { MessageSquarePlus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Badge, Button, ErrorNote, Field, inputClass, Panel, ShowAll } from "@/components/ui";
import { api } from "@/lib/client";
import { formatDate, label, money } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { DealOutcome, Opportunity, SalesFeedback } from "@/lib/types";

const POSITIVE = new Set(["good_lead", "meeting_booked", "proposal_sent", "won", "opportunity_confirmed", "contacted"]);
const NEGATIVE = new Set(["bad_lead", "lost", "wrong_buyer", "wrong_service", "not_icp", "duplicate", "competitor", "opportunity_incorrect"]);

function tone(kind: string) {
  return POSITIVE.has(kind) ? "green" : NEGATIVE.has(kind) ? "red" : "amber";
}

/** §15 salesperson feedback on an account: stored for the learning engine, nothing else. */
export function SalesFeedbackPanel({ accountId, opportunities }: { accountId: string; opportunities: Opportunity[] }) {
  const { data: kinds } = useApi<{ key: string; label: string }[]>("/sales-feedback/kinds");
  const { data } = useApi<SalesFeedback[]>(`/accounts/${accountId}/sales-feedback`);
  const { busy, error, run } = useAction();
  const [giving, setGiving] = useState(false);
  const [all, setAll] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const saved = await run(() =>
      api(`/accounts/${accountId}/sales-feedback`, {
        method: "POST",
        body: {
          kind: values.get("kind"),
          opportunity_id: String(values.get("opportunity") ?? "") || null,
          note: String(values.get("note") ?? "").trim() || null,
        },
      }).then(() => true),
    );
    if (saved) {
      form.reset();
      setGiving(false);
    }
  }

  const shown = all ? data : data?.slice(0, 4);
  return (
    <Panel
      title="Feedback"
      description="How good this lead really is. Kept for the learning engine; it changes nothing by itself."
      testId="sales-feedback"
      actions={
        !giving && (
          <Button onClick={() => setGiving(true)} icon={<MessageSquarePlus className="h-4 w-4" />}>
            Give feedback
          </Button>
        )
      }
      footer={data && data.length > 4 && !all && <ShowAll onClick={() => setAll(true)}>All {data.length} pieces of feedback</ShowAll>}
    >
      <div className="space-y-3">
        {giving && (
          <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5" data-testid="feedback-form">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Your feedback">
                <select name="kind" required defaultValue="" className={inputClass}>
                  <option value="" disabled>
                    Choose
                  </option>
                  {kinds?.map((k) => (
                    <option key={k.key} value={k.key}>
                      {k.label}
                    </option>
                  ))}
                </select>
              </Field>
              {opportunities.length > 0 && (
                <Field label="About (optional)">
                  <select name="opportunity" defaultValue="" className={inputClass}>
                    <option value="">The account as a whole</option>
                    {opportunities.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
            </div>
            <Field label="Why (optional)">
              <input name="note" maxLength={2000} className={inputClass} />
            </Field>
            <ErrorNote error={error} />
            <div className="flex gap-2">
              <Button type="submit" variant="primary" busy={busy}>
                Save feedback
              </Button>
              <Button variant="ghost" onClick={() => setGiving(false)}>
                Cancel
              </Button>
            </div>
          </form>
        )}
        {shown && shown.length > 0 ? (
          <ul className="divide-y divide-grid" data-testid="feedback-list">
            {shown.map((f) => (
              <li key={f.id} className="flex flex-wrap items-start gap-2 py-2 text-[13px] first:pt-0 last:pb-0">
                <Badge tone={tone(f.kind)}>{f.label}</Badge>
                <span className="min-w-0 flex-1 text-fg-2">
                  {f.note}
                  <span className="block text-xs text-fg-3">
                    {f.given_by ?? "Someone"} · {formatDate(f.created_at)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          !giving && <p className="text-[13px] text-fg-3">No feedback yet.</p>
        )}
      </div>
    </Panel>
  );
}

/** What was true when a deal was won or lost (§13), as recorded at the close. */
export function DealOutcomeSummary({ dealId }: { dealId: string }) {
  const { data } = useApi<DealOutcome | null>(`/deals/${dealId}/outcome`);
  if (!data) return null;
  const rows: [string, string][] = [
    ["Service", data.service ?? "Unknown"],
    ["Opportunity", data.opportunity_type ?? "Unknown"],
    ["Industry", data.industry ?? "Unknown"],
    ["Size", data.company_size_band ?? "Unknown"],
    ["Country", data.hq_country ?? "Unknown"],
    ["Source", data.source ? label(data.source) : "Unknown"],
    ["Buyer", data.buyer_role ? label(data.buyer_role) : "Unknown"],
    ["Sales cycle", `${data.deal_days} days as a deal${data.lead_days !== null ? `, ${data.lead_days} from qualified` : ""}`],
    ["Value", money(data.value, data.currency)],
    ["Priority then", data.close_scores?.priority_score != null ? String(Math.round(data.close_scores.priority_score)) : "Unknown"],
    ["Similar client", data.reference_project ?? "None found"],
  ];
  return (
    <div className="space-y-2 border-t border-grid pt-4" data-testid="deal-outcome">
      <h3 className="text-[13px] font-semibold text-fg">
        When it was {data.outcome} ({formatDate(data.closed_at)})
      </h3>
      {data.captured_late && (
        <p className="text-xs text-warn">Recorded after the close: these facts are as they were when recorded, which may differ from the close.</p>
      )}
      <dl className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-fg-3">{k}</dt>
            <dd className="text-fg-2">{v}</dd>
          </div>
        ))}
        <dt className="text-fg-3">Signals</dt>
        <dd className="text-fg-2">{data.signals.length ? data.signals.map((s) => label(s.signal)).join(", ") : "None in the 6 months before"}</dd>
      </dl>
    </div>
  );
}
