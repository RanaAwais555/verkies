"use client";

import { Check, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button, Checkbox, ErrorNote, Field, inputClass, Panel } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api, ApiError } from "@/lib/client";
import { endOfWorkingDay } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Approval, Duplicate, Session, TeamMember } from "@/lib/types";
import { REJECTION_REASONS } from "@/lib/types";

type Props = {
  runId: string;
  session: Session;
  nextAction: string | null;
  needsOverride: boolean;
  recommendedRejection: string | null;
  /** Called after the decision is saved; the page then shows the outcome instead of this panel. */
  onDecided: (approval?: Approval) => Promise<unknown>;
};

/** Approve a researched prospect into the CRM, or reject it with a reason. */
export function DecisionPanel(props: Props) {
  // When the engines did not qualify the prospect, open on Reject with their reason chosen.
  const [mode, setMode] = useState<"approve" | "reject">(props.needsOverride ? "reject" : "approve");
  const toggle = (key: "approve" | "reject", text: string) => (
    <button
      type="button"
      onClick={() => setMode(key)}
      aria-pressed={mode === key}
      className={cx(
        "h-8 rounded-md px-3.5 text-[13px] font-medium transition-colors duration-200 ease-spring",
        mode === key ? (key === "approve" ? "bg-ok text-white" : "bg-bad text-white") : "text-fg-2 hover:text-fg",
      )}
    >
      {text}
    </button>
  );
  return (
    <Panel
      primary
      title="Decision"
      description="Approving creates the account, lead, contacts and a dated next action in one step."
      actions={
        <div role="group" aria-label="Decision" className="flex gap-1 rounded-lg border border-border-strong bg-surface-2 p-0.5">
          {toggle("approve", "Approve")}
          {toggle("reject", "Reject")}
        </div>
      }
    >
      {mode === "approve" ? <ApproveForm {...props} /> : <RejectForm {...props} />}
    </Panel>
  );
}

function ApproveForm({ runId, session, nextAction, needsOverride, onDecided }: Props) {
  const { data: team } = useApi<TeamMember[]>("/team");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [duplicates, setDuplicates] = useState<Duplicate[] | null>(null);

  async function approve(form: HTMLFormElement, choice: { account_id?: string; create_new_account?: boolean } = {}) {
    const data = new FormData(form);
    const body = {
      owner_id: data.get("owner") || null,
      task_title: String(data.get("title") ?? "").trim() || null,
      due_at: endOfWorkingDay(String(data.get("due") ?? "")),
      override_reason: String(data.get("override") ?? "").trim() || null,
      ...choice,
    };
    setBusy(true);
    setError(null);
    try {
      await onDecided(await api<Approval>(`/prospects/${runId}/approve`, { method: "POST", body }));
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

  return (
    <form
      className="space-y-4"
      onSubmit={(e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        approve(e.currentTarget);
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Owner">
          {/* Re-mounted when the team arrives, so the default owner applies to real options. */}
          <select key={team ? "team" : "loading"} name="owner" defaultValue={session.user.id} className={inputClass}>
            {(team ?? [{ id: session.user.id, name: session.user.name, email: session.user.email }]).map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Next action due" hint="Leave empty for the default: two working days.">
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
        <div className="space-y-3 rounded-xl border border-violet/40 bg-violet-soft/50 p-3.5 text-[13px]" data-testid="duplicates">
          <p className="font-medium text-fg">This may be a company you already have. Choose one:</p>
          <ul className="space-y-2">
            {duplicates.map((d) => (
              <li key={d.account_id} className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-fg">{d.name}</span>
                <span className="text-xs text-fg-3">
                  {d.primary_domain ?? "no domain"} · matched by {d.match}
                </span>
                <Button busy={busy} onClick={(e) => approve(e.currentTarget.form!, { account_id: d.account_id })}>
                  Add to this account
                </Button>
              </li>
            ))}
          </ul>
          <Button busy={busy} onClick={(e) => approve(e.currentTarget.form!, { create_new_account: true })}>
            It is a different company: create a new account
          </Button>
        </div>
      )}
      <ErrorNote error={error} />
      {!duplicates && (
        <Button type="submit" variant="primary" busy={busy} icon={<Check className="h-4 w-4" />}>
          Approve and create the account
        </Button>
      )}
    </form>
  );
}

function RejectForm({ runId, recommendedRejection, onDecided }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

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
      await onDecided();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Reason">
        <select name="reason" defaultValue={recommendedRejection ?? "no_commercial_opportunity"} className={inputClass}>
          {Object.entries(REJECTION_REASONS).map(([key, text]) => (
            <option key={key} value={key}>
              {text}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Note (optional)">
        <textarea name="note" rows={2} maxLength={2000} className={inputClass} />
      </Field>
      <Checkbox name="suppress" label="Never research or contact this domain again" />
      <ErrorNote error={error} />
      <Button type="submit" variant="danger" busy={busy} icon={<X className="h-4 w-4" />}>
        Reject
      </Button>
    </form>
  );
}
