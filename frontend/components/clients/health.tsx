"use client";

import { HeartPulse, MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Badge, Button, Empty, ErrorNote, Field, inputClass, Panel, ShowAll, Table, type Tone } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { formatDate, relativeDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Account360, AccountHealth, ClientSummary, HealthColour, HealthReason } from "@/lib/types";

const COLOUR: Record<HealthColour, { label: string; tone: Tone; dot: string }> = {
  green: { label: "Green", tone: "green", dot: "bg-ok" },
  yellow: { label: "Yellow", tone: "amber", dot: "bg-warn" },
  red: { label: "Red", tone: "red", dot: "bg-bad" },
};

const SENTIMENT: Record<string, { label: string; tone: Tone }> = {
  positive: { label: "Positive", tone: "green" },
  neutral: { label: "Neutral", tone: "neutral" },
  negative: { label: "Negative", tone: "red" },
};

/** Client health (§14), always with its word as well as its colour. */
export function HealthBadge({ colour }: { colour: HealthColour }) {
  const c = COLOUR[colour];
  return (
    <Badge tone={c.tone} title={`Client health: ${c.label}`}>
      <span aria-hidden className={cx("h-1.5 w-1.5 rounded-full", c.dot)} />
      {c.label}
    </Badge>
  );
}

export function Reasons({ reasons, limit }: { reasons: HealthReason[]; limit?: number }) {
  if (reasons.length === 0) return <p className="text-xs text-fg-3">Nothing needs attention.</p>;
  const shown = limit ? reasons.slice(0, limit) : reasons;
  return (
    <ul className="space-y-0.5 text-xs">
      {shown.map((r) => (
        <li key={r.text} className={r.level === "red" ? "text-bad" : "text-warn"}>
          {r.text}
        </li>
      ))}
      {limit && reasons.length > limit && <li className="text-fg-3">and {reasons.length - limit} more</li>}
    </ul>
  );
}

/** Every client with its health, worst first. */
export function ClientTable({ clients }: { clients: ClientSummary[] }) {
  return (
    <Table testId="clients">
      <thead>
        <tr>
          <th>Client</th>
          <th>Health</th>
          <th>Why</th>
          <th>Account manager</th>
          <th>Last contact</th>
          <th>Projects</th>
        </tr>
      </thead>
      <tbody>
        {clients.map((c) => (
          <tr key={c.account_id} data-testid="client-row">
            <td className="min-w-[12rem]">
              <Link href={`/accounts/${c.account_id}?tab=client`} className="font-medium text-fg hover:text-accent-text hover:underline">
                {c.name}
              </Link>
              <span className="block text-xs text-fg-3">{c.client_since ? `Client since ${formatDate(c.client_since)}` : c.primary_domain}</span>
            </td>
            <td>
              <HealthBadge colour={c.health} />
            </td>
            <td className="min-w-[16rem]">
              <Reasons reasons={c.reasons} limit={2} />
            </td>
            <td className="whitespace-nowrap text-fg-2">{c.account_manager?.name ?? <span className="text-fg-3">Not set</span>}</td>
            <td className="whitespace-nowrap text-fg-2" title={formatDate(c.last_contact_at, true)}>
              {c.last_contact_at ? relativeDate(c.last_contact_at) : <span className="text-fg-3">Never logged</span>}
            </td>
            <td className="tabular text-fg-2">{c.open_projects}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

function FeedbackForm({ accountId, onDone }: { accountId: string; onDone: () => void }) {
  const { busy, error, run } = useAction();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const saved = await run(() =>
      api(`/accounts/${accountId}/feedback`, {
        method: "POST",
        body: {
          sentiment: data.get("sentiment"),
          note: String(data.get("note") ?? "").trim() || null,
          received_on: String(data.get("on") ?? "") || null,
        },
      }).then(() => true),
    );
    if (saved) {
      form.reset();
      onDone();
    }
  }
  return (
    <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5" data-testid="feedback-form">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="How they feel">
          <select name="sentiment" required defaultValue="" className={inputClass}>
            <option value="" disabled>
              Choose
            </option>
            <option value="positive">Positive</option>
            <option value="neutral">Neutral</option>
            <option value="negative">Negative</option>
          </select>
        </Field>
        <Field label="When they said it">
          <input name="on" type="date" className={inputClass} />
        </Field>
      </div>
      <Field label="What they said (optional)">
        <textarea name="note" maxLength={4000} rows={2} className={cx(inputClass, "resize-y")} />
      </Field>
      <ErrorNote error={error} />
      <Button type="submit" variant="primary" busy={busy}>
        Record feedback
      </Button>
    </form>
  );
}

function EndClient({ accountId, onDone }: { accountId: string; onDone: () => void }) {
  const { busy, error, run } = useAction();
  const [open, setOpen] = useState(false);
  if (!open)
    return (
      <Button variant="ghost" className="h-7 px-2.5 text-xs" onClick={() => setOpen(true)}>
        No longer a client
      </Button>
    );
  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
        if (await run(() => api(`/accounts/${accountId}/end-client`, { method: "POST", body: { reason } }).then(() => true))) onDone();
      }}
      className="animate-rise space-y-3 rounded-xl border border-bad/30 bg-bad-soft p-3.5"
    >
      <p className="text-[13px] text-fg">The account becomes a former client and keeps all its history. Open projects must be finished or cancelled first.</p>
      <Field label="Why the relationship ended">
        <input name="reason" required minLength={3} maxLength={500} className={inputClass} />
      </Field>
      <ErrorNote error={error} />
      <div className="flex gap-2">
        <Button type="submit" variant="danger" busy={busy}>
          Mark as former client
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** The account's client health: colour and reasons, feedback, and how the colour has changed. */
export function ClientHealthPanel({ account, onChange }: { account: Account360; onChange: () => void }) {
  const { data, error, mutate } = useApi<AccountHealth>(`/accounts/${account.id}/health`);
  const [recording, setRecording] = useState(false);
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;
  const current = data.current;
  if (!current && data.feedback.length === 0 && data.history.length === 0) return null;
  const refresh = () => {
    void mutate();
    onChange();
  };

  return (
    <Panel
      title="Client health"
      description="Read from projects, milestones, risks, tasks, contact and the client's own feedback. Checked every morning; a client turning Red gets a follow-up task."
      testId="client-health"
      actions={
        current &&
        !recording && (
          <Button onClick={() => setRecording(true)} icon={<MessageSquareText className="h-4 w-4" />}>
            Record feedback
          </Button>
        )
      }
    >
      <div className="space-y-4">
        {current ? (
          <div className="flex flex-wrap items-start gap-3">
            <HealthBadge colour={current.health} />
            <div className="min-w-0 flex-1">
              <Reasons reasons={current.reasons} />
            </div>
          </div>
        ) : (
          <p className="text-[13px] text-fg-2">Not a current client.</p>
        )}
        {recording && (
          <FeedbackForm
            accountId={account.id}
            onDone={() => {
              setRecording(false);
              refresh();
            }}
          />
        )}
        {data.feedback.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-[13px] font-semibold text-fg">Feedback</h3>
            <ul className="divide-y divide-grid" data-testid="feedback">
              {data.feedback.map((f) => (
                <li key={f.id} className="flex flex-wrap items-start gap-2 py-2 text-[13px] first:pt-0 last:pb-0">
                  <Badge tone={SENTIMENT[f.sentiment].tone}>{SENTIMENT[f.sentiment].label}</Badge>
                  <span className="min-w-0 flex-1 text-fg-2">
                    {f.note ?? <span className="text-fg-3">No note</span>}
                    <span className="block text-xs text-fg-3">
                      {formatDate(f.received_on)}
                      {f.recorded_by && ` · recorded by ${f.recorded_by}`}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {data.history.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-[13px] font-semibold text-fg">History</h3>
            <ol className="space-y-1.5" data-testid="health-history">
              {data.history.map((h) => (
                <li key={h.assessed_at} className="flex flex-wrap items-center gap-2 text-xs text-fg-3">
                  <span className="tabular">{formatDate(h.assessed_at)}</span>
                  <HealthBadge colour={h.colour} />
                  {h.reasons[0] && <span className="min-w-0 flex-1 text-fg-2">{h.reasons[0].text}</span>}
                </li>
              ))}
            </ol>
          </div>
        )}
        {current && <EndClient accountId={account.id} onDone={refresh} />}
      </div>
    </Panel>
  );
}

/** Red clients on the Command Center; nothing at all when there are none. */
export function ClientRisks() {
  const { data } = useApi<ClientSummary[]>("/clients?health=red");
  if (!data || data.length === 0) return null;
  return (
    <Panel title="Clients at risk" footer={<ShowAll href="/clients?health=red">All clients at risk</ShowAll>} testId="client-risks">
      <ul className="divide-y divide-grid">
        {data.slice(0, 5).map((c) => (
          <li key={c.account_id} className="space-y-1 py-2.5 first:pt-0 last:pb-0">
            <Link href={`/accounts/${c.account_id}?tab=client`} className="flex items-center gap-2 text-[13px] font-medium text-fg hover:text-accent-text">
              <HeartPulse aria-hidden className="h-3.5 w-3.5 text-bad" />
              {c.name}
            </Link>
            <Reasons reasons={c.reasons} limit={1} />
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function NoClients() {
  return <Empty icon={<HeartPulse className="h-4 w-4" />}>No clients here. An account becomes a client when a won deal is converted.</Empty>;
}
