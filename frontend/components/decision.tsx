"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button, Card, ErrorNote, Field, formatDate, inputClass } from "@/components/ui";
import { api, ApiError } from "@/lib/client";
import { useApi } from "@/lib/hooks";
import type { Approval, Duplicate, Session, TeamMember } from "@/lib/types";
import { REJECTION_REASONS } from "@/lib/types";

type Props = {
  runId: string;
  session: Session;
  nextAction: string | null;
  needsOverride: boolean;
  recommendedRejection: string | null;
  onDecided: () => void;
};

export function DecisionPanel(props: Props) {
  const [mode, setMode] = useState<"approve" | "reject">(props.needsOverride ? "reject" : "approve");
  return (
    <Card title="Decision" actions={
      <div className="flex gap-1" role="group" aria-label="Decision">
        <Button variant={mode === "approve" ? "primary" : "secondary"} onClick={() => setMode("approve")}>Approve</Button>
        <Button variant={mode === "reject" ? "danger" : "secondary"} onClick={() => setMode("reject")}>Reject</Button>
      </div>
    }>
      {mode === "approve" ? <ApproveForm {...props} /> : <RejectForm {...props} />}
    </Card>
  );
}

function ApproveForm({ runId, session, nextAction, needsOverride, onDecided }: Props) {
  const { data: team } = useApi<TeamMember[]>("/team");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [duplicates, setDuplicates] = useState<Duplicate[] | null>(null);
  const [done, setDone] = useState<Approval | null>(null);

  async function approve(form: HTMLFormElement, choice: { account_id?: string; create_new_account?: boolean } = {}) {
    const data = new FormData(form);
    const due = String(data.get("due") ?? "");
    const body = {
      owner_id: data.get("owner") || null,
      task_title: String(data.get("title") ?? "").trim() || null,
      // A chosen date is due at the end of that working day, local time.
      due_at: due ? new Date(`${due}T17:00:00`).toISOString() : null,
      override_reason: String(data.get("override") ?? "").trim() || null,
      ...choice,
    };
    setBusy(true);
    setError(null);
    try {
      setDone(await api<Approval>(`/prospects/${runId}/approve`, { method: "POST", body }));
      onDecided();
    } catch (err) {
      if (err instanceof ApiError && err.code === "possible_duplicate") {
        setDuplicates((err.details?.possible_duplicates as Duplicate[]) ?? []);
      } else {
        setError(err);
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="space-y-2 text-sm" data-testid="approved">
        <p>
          Approved. {done.created_account ? "New account created" : "Added to the existing account"} with a lead,
          {done.opportunity_id ? " an opportunity," : ""} {done.contact_ids.length} contact{done.contact_ids.length === 1 ? "" : "s"} and
          a task due {formatDate(done.task_due_at)}.
        </p>
        <Link href={`/accounts/${done.account_id}`} className="font-medium underline">Open the account</Link>
      </div>
    );
  }

  return (
    <form
      className="space-y-3"
      onSubmit={(e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        approve(e.currentTarget);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Owner">
          <select key={team ? "team" : "loading"} name="owner" defaultValue={session.user.id} className={inputClass}>
            {(team ?? [{ id: session.user.id, name: session.user.name, email: session.user.email }]).map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Next action due" hint="Leave empty for the default (2 business days).">
          <input name="due" type="date" className={inputClass} />
        </Field>
      </div>
      <Field label="Next action">
        <input name="title" defaultValue={nextAction ?? ""} maxLength={200} className={inputClass} />
      </Field>
      {needsOverride && (
        <Field label="Why approve anyway?" hint="The engines did not qualify this prospect. Your reason is kept in the audit log.">
          <textarea name="override" required minLength={10} rows={2} className={inputClass} />
        </Field>
      )}
      {duplicates && (
        <div className="space-y-2 rounded-md border border-purple-300 p-3 text-sm dark:border-purple-900" data-testid="duplicates">
          <p className="font-medium">This may be a company you already have. Choose one:</p>
          <ul className="space-y-1">
            {duplicates.map((d) => (
              <li key={d.account_id} className="flex flex-wrap items-center gap-2">
                <span>{d.name}</span>
                <span className="text-xs text-muted">{d.primary_domain ?? "no domain"} · matched by {d.match}</span>
                <Button type="button" variant="secondary" busy={busy} onClick={(e) => approve(e.currentTarget.form!, { account_id: d.account_id })}>
                  Add to this account
                </Button>
              </li>
            ))}
          </ul>
          <Button type="button" variant="secondary" busy={busy} onClick={(e) => approve(e.currentTarget.form!, { create_new_account: true })}>
            It is a different company: create a new account
          </Button>
        </div>
      )}
      <ErrorNote error={error} />
      {!duplicates && <Button type="submit" busy={busy}>Approve and create the account</Button>}
    </form>
  );
}

function RejectForm({ runId, recommendedRejection, onDecided }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api(`/prospects/${runId}/reject`, {
        method: "POST",
        body: { reason: data.get("reason"), note: String(data.get("note") ?? "").trim() || null, suppress: data.get("suppress") === "on" },
      });
      setDone(true);
      onDecided();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (done) return <p className="text-sm" data-testid="rejected">Rejected. It is off the queue and stays searchable under Research.</p>;
  return (
    <form onSubmit={submit} className="space-y-3">
      <Field label="Reason">
        <select name="reason" defaultValue={recommendedRejection ?? "no_commercial_opportunity"} className={inputClass}>
          {Object.entries(REJECTION_REASONS).map(([key, text]) => <option key={key} value={key}>{text}</option>)}
        </select>
      </Field>
      <Field label="Note (optional)">
        <textarea name="note" rows={2} maxLength={2000} className={inputClass} />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="suppress" /> Never research or contact this domain again
      </label>
      <ErrorNote error={error} />
      <Button type="submit" variant="danger" busy={busy}>Reject</Button>
    </form>
  );
}
