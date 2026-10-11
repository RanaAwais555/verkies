"use client";

import { CalendarDays, Mail, MessageSquare, NotebookPen, Phone, PhoneIncoming, PhoneMissed, Plus, type LucideIcon } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Badge, Button, Checkbox, Empty, ErrorNote, Field, inputClass, Skeleton } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { endOfWorkingDay, formatDate, relativeDate } from "@/lib/format";
import { useAction, useApi, useSession } from "@/lib/hooks";
import type { Account360, Activity, ActivityKind, Deal, Relationship, TeamMember } from "@/lib/types";

const KINDS: { key: ActivityKind; label: string; icon: LucideIcon }[] = [
  { key: "call", label: "Call", icon: Phone },
  { key: "meeting", label: "Meeting", icon: CalendarDays },
  { key: "message", label: "Message", icon: MessageSquare },
  { key: "note", label: "Note", icon: NotebookPen },
];

const CHANNELS = [
  { key: "email", label: "Email" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "whatsapp", label: "WhatsApp" },
  { key: "other", label: "Other" },
];

const CHANNEL_LABEL: Record<string, string> = {
  email: "Email",
  linkedin: "LinkedIn message",
  whatsapp: "WhatsApp message",
  manual: "Message",
};
const OUTCOME_LABEL = {
  connected: "connected",
  no_answer: "no answer",
  voicemail: "left a voicemail",
} as const;

/** The local date and time now, in the shape a datetime-local input takes. */
function localNow(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

// --- relationship ------------------------------------------------------------------------------

const STATUS: Record<Relationship["response_status"], { label: string; tone: "neutral" | "amber" | "green" }> = {
  not_contacted: { label: "Not contacted yet", tone: "neutral" },
  no_reply: { label: "No reply yet", tone: "amber" },
  awaiting_reply: { label: "Awaiting reply", tone: "amber" },
  replied: { label: "Replied", tone: "green" },
};

/** Relationship tracking in one line: response status, attempts, interactions and last contact. */
export function RelationshipLine({ relationship: r, className }: { relationship: Relationship; className?: string }) {
  const status = STATUS[r.response_status];
  const attempts = r.attempts_since_reply;
  return (
    <span className={cx("inline-flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3", className)} data-testid="relationship">
      <Badge tone={status.tone}>{status.label}</Badge>
      {attempts > 0 && (
        <span>
          {attempts} {attempts === 1 ? "attempt" : "attempts"}
          {r.response_status === "awaiting_reply" && " since their last reply"}
        </span>
      )}
      {r.interactions > 0 && (
        <>
          <span>
            · {r.interactions} {r.interactions === 1 ? "interaction" : "interactions"}
          </span>
          <span title={formatDate(r.latest_interaction_at, true)}>· last {relativeDate(r.latest_interaction_at).toLowerCase()}</span>
        </>
      )}
    </span>
  );
}

// --- logging -----------------------------------------------------------------------------------

/**
 * Log something that already happened: a call, meeting, message or note. VROS records it; it never
 * contacts anyone itself. A follow-up can be scheduled in the same step, and becomes the next task
 * of the deal or opportunity the activity is about.
 */
export function LogActivityForm({
  accountId,
  dealId,
  contactId,
  onLogged,
  onCancel,
}: {
  accountId: string;
  /** Log against this deal; the "About" choice is hidden. */
  dealId?: string;
  contactId?: string;
  onLogged?: () => void;
  onCancel?: () => void;
}) {
  const { data: session } = useSession();
  const { data: account } = useApi<Account360>(`/accounts/${accountId}`);
  const { data: deals } = useApi<Deal[]>(dealId ? null : `/deals?account_id=${accountId}&status=all`);
  const { data: team } = useApi<TeamMember[]>("/team");
  const { busy, error, run } = useAction();
  const [kind, setKind] = useState<ActivityKind>("call");
  const [followUp, setFollowUp] = useState(false);
  const [when, setWhen] = useState(localNow);

  const opportunitiesWithoutDeal = (account?.opportunities ?? []).filter((o) => !deals?.some((d) => d.opportunity_id === o.id));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const about = String(data.get("about") ?? "");
    const logged = await run(() =>
      api("/activities", {
        method: "POST",
        body: {
          account_id: accountId,
          kind,
          summary: String(data.get("summary") ?? "").trim(),
          occurred_at: when ? new Date(when).toISOString() : null,
          contact_id: data.get("contact") || null,
          deal_id: dealId ?? (about.startsWith("deal:") ? about.slice(5) : null),
          opportunity_id: about.startsWith("opp:") ? about.slice(4) : null,
          call_outcome: kind === "call" ? data.get("outcome") : null,
          message_channel: kind === "message" ? data.get("channel") : null,
          received: kind === "message" && data.get("sender") === "them",
          follow_up: followUp
            ? {
                title: String(data.get("follow_title") ?? "").trim(),
                due_at: endOfWorkingDay(String(data.get("follow_due") ?? "")),
                owner_id: data.get("follow_owner") || null,
              }
            : null,
        },
      }).then(() => true),
    );
    if (!logged) return;
    form.reset();
    setFollowUp(false);
    setWhen(localNow());
    onLogged?.(); // the API client revalidates every list after a write
  }

  const kindLabel = KINDS.find((k) => k.key === kind)!.label.toLowerCase();
  return (
    <form onSubmit={submit} className="@container animate-rise space-y-3.5" data-testid="log-activity">
      <fieldset>
        <legend className="mb-1.5 text-[12.5px] font-medium text-fg-2">What happened</legend>
        <div className="grid grid-cols-2 gap-1 rounded-[10px] border border-border bg-surface-2 p-1 @md:inline-grid @md:grid-cols-4">
          {KINDS.map(({ key, label, icon: Icon }) => (
            <label
              key={key}
              className={cx(
                "relative flex cursor-pointer items-center justify-center gap-1.5 rounded-[7px] px-3 py-1.5 text-[13px] font-medium transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent",
                kind === key ? "bg-surface text-fg shadow-[var(--lift)]" : "text-fg-3 hover:text-fg",
              )}
            >
              {/* The real radio covers the whole segment, invisibly, so a click or tap always lands on it. */}
              <input
                type="radio"
                name="kind"
                value={key}
                checked={kind === key}
                onChange={() => setKind(key)}
                className="absolute inset-0 m-0 cursor-pointer appearance-none rounded-[7px] opacity-0"
              />
              <Icon aria-hidden className="h-3.5 w-3.5" />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-3 @lg:grid-cols-2">
        <Field label={kind === "note" ? "About whom (optional)" : "With"}>
          <select key={account ? "ready" : "loading"} name="contact" defaultValue={contactId ?? ""} className={inputClass}>
            <option value="">{kind === "note" ? "Nobody in particular" : "Someone not listed"}</option>
            {account?.contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.title ? `, ${c.title}` : ""}
              </option>
            ))}
          </select>
        </Field>
        <Field label="When">
          <input name="when" type="datetime-local" required value={when} max={localNow()} onChange={(e) => setWhen(e.target.value)} className={inputClass} />
        </Field>
        {kind === "call" && (
          <Field label="How it went">
            <select name="outcome" required defaultValue="" className={inputClass}>
              <option value="" disabled>
                Choose
              </option>
              <option value="connected">Connected, we spoke</option>
              <option value="no_answer">No answer</option>
              <option value="voicemail">Left a voicemail</option>
            </select>
          </Field>
        )}
        {kind === "message" && (
          <>
            <Field label="Channel">
              <select name="channel" required defaultValue="email" className={inputClass}>
                {CHANNELS.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Sent by">
              <select name="sender" defaultValue="us" className={inputClass}>
                <option value="us">Us</option>
                <option value="them">Them (a reply or inbound message)</option>
              </select>
            </Field>
          </>
        )}
        {!dealId && (
          <Field label="About" className={kind === "message" ? "@lg:col-span-2" : undefined}>
            <select key={deals && account ? "ready" : "loading"} name="about" defaultValue="" className={inputClass}>
              <option value="">The account in general</option>
              {deals?.map((d) => (
                <option key={d.id} value={`deal:${d.id}`}>
                  Deal: {d.name} ({d.stage_name})
                </option>
              ))}
              {opportunitiesWithoutDeal.map((o) => (
                <option key={o.id} value={`opp:${o.id}`}>
                  Opportunity: {o.name}
                </option>
              ))}
            </select>
          </Field>
        )}
      </div>

      <Field label={kind === "note" ? "Note" : "What was said or agreed"}>
        <textarea name="summary" required maxLength={4000} rows={3} className={cx(inputClass, "resize-y leading-relaxed")} />
      </Field>

      <div className="space-y-3 rounded-xl border border-border bg-surface-2 p-3">
        <Checkbox label="Schedule a follow-up" checked={followUp} onChange={(e) => setFollowUp(e.target.checked)} />
        {followUp && (
          <div className="grid gap-3 @xl:grid-cols-[minmax(0,1fr)_150px_170px]">
            <Field label="Follow-up">
              <input name="follow_title" required maxLength={200} className={inputClass} />
            </Field>
            <Field label="Due">
              <input name="follow_due" type="date" required className={inputClass} />
            </Field>
            <Field label="Owner">
              <select key={team ? "team" : "loading"} name="follow_owner" defaultValue={session?.user.id ?? ""} className={inputClass}>
                {team?.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}
      </div>

      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={busy} icon={<Plus className="h-4 w-4" />}>
          Log {kindLabel}
        </Button>
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

// --- reading -----------------------------------------------------------------------------------

function iconOf(a: Activity): LucideIcon {
  if (a.kind === "call") return a.call_outcome === "connected" ? PhoneIncoming : PhoneMissed;
  if (a.kind === "meeting") return CalendarDays;
  if (a.kind === "note") return NotebookPen;
  return a.channel === "email" ? Mail : MessageSquare;
}

function headline(a: Activity): string {
  const who = a.contact?.name;
  if (a.kind === "call") return `Call${who ? ` with ${who}` : ""}, ${a.call_outcome ? OUTCOME_LABEL[a.call_outcome] : "outcome unknown"}`;
  if (a.kind === "meeting") return `Meeting${who ? ` with ${who}` : ""}`;
  if (a.kind === "note") return `Note${who ? ` about ${who}` : ""}`;
  const channel = CHANNEL_LABEL[a.channel] ?? "Message";
  const inbound = a.direction === "inbound";
  return who ? `${channel} ${inbound ? "from" : "to"} ${who}` : `${channel} ${inbound ? "received" : "sent"}`;
}

/** Logged activities, newest first. `query` picks whose: `account_id=…`, `deal_id=…` or `contact_id=…`. */
export function ActivityList({ query, limit = 100, empty = "Nothing logged yet." }: { query: string; limit?: number; empty?: string }) {
  const { data, error } = useApi<Activity[]>(`/activities?${query}&limit=${limit}`);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={3} />;
  if (data.length === 0) return <Empty icon={<NotebookPen className="h-4 w-4" />}>{empty}</Empty>;
  return (
    <ul className="divide-y divide-grid" data-testid="activities">
      {data.map((a) => {
        const Icon = iconOf(a);
        const reply = a.direction === "inbound" || a.direction === "conversation";
        return (
          <li key={a.id} className="flex gap-3 py-3 first:pt-0 last:pb-0" data-testid="activity">
            <span
              aria-hidden
              className={cx(
                "mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-[9px]",
                a.direction === "internal" ? "bg-sunken text-fg-3" : reply ? "bg-ok-soft text-ok" : "bg-accent-soft text-accent-text",
              )}
            >
              <Icon className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1 space-y-0.5">
              <p className="text-[13px] font-medium text-fg">{headline(a)}</p>
              <p className="whitespace-pre-line text-[13px] leading-relaxed text-fg-2">{a.summary}</p>
              <p className="text-xs text-fg-3">
                <time dateTime={a.occurred_at}>{formatDate(a.occurred_at, true)}</time> · logged by {a.logged_by?.name ?? "VROS"}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
