"use client";

import { CheckCircle2, CircleX, Copy, ExternalLink, Linkedin, Mail, Phone, Send, SkipForward } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Badge, BandBadge, Button, Empty, ErrorNote, Field, inputClass, Note, Skeleton } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { formatDate } from "@/lib/format";
import { useAction, useApi, useCanChange } from "@/lib/hooks";
import type { EmailPreflight, OutreachQueue, OutreachQueueItem } from "@/lib/types";

const CHANNEL = {
  email: { label: "Email", icon: Mail },
  linkedin: { label: "LinkedIn", icon: Linkedin },
  call: { label: "Call", icon: Phone },
} as const;

/** Variables a person still has to write: shown, never guessed. */
function Missing({ names }: { names: string[] }) {
  if (names.length === 0) return null;
  return (
    <Note>
      VROS has nothing to fill {names.map((n) => (n === "subject" ? "the subject" : `{${n}}`)).join(", ")} with. Write it yourself or remove it before sending.
    </Note>
  );
}

function EmailStep({ item, onDone }: { item: OutreachQueueItem; onDone: () => void }) {
  const { data: checks } = useApi<EmailPreflight>(`/email/preflight?contact_id=${item.contact_id}`);
  const { busy, error, run } = useAction();
  const [subject, setSubject] = useState(item.draft.subject ?? "");
  const [body, setBody] = useState(item.draft.body);
  const unfilled = /\{(first_name|name|title|company|sender_name|why_now|problem|service|similar_project)\}/.test(`${subject}\n${body}`);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      await run(() => api(`/outreach/enrollments/${item.enrollment_id}/steps`, { method: "POST", body: { action: "email", subject, body } }).then(() => true))
    )
      onDone();
  }

  const failing = checks?.checks.filter((c) => !c.ok) ?? [];
  return (
    <form onSubmit={send} className="space-y-3">
      <Missing names={item.draft.missing} />
      <Field label="Subject">
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          required
          maxLength={300}
          readOnly={!!item.draft.reply_to_id}
          className={inputClass}
        />
      </Field>
      <Field label="Message">
        <textarea value={body} onChange={(e) => setBody(e.target.value)} required rows={7} className={cx(inputClass, "resize-y leading-relaxed")} />
      </Field>
      {checks && failing.length > 0 && (
        <ul className="space-y-1" aria-label="Checks before sending">
          {failing.map((c) => (
            <li key={c.key} className="flex items-start gap-1.5 text-xs text-bad">
              <CircleX aria-hidden className="mt-px h-3.5 w-3.5 shrink-0" />
              {c.message}
            </li>
          ))}
        </ul>
      )}
      {checks?.ok && (
        <p className="flex items-center gap-1.5 text-xs text-fg-3">
          <CheckCircle2 aria-hidden className="h-3.5 w-3.5 text-ok" />
          All {checks.checks.length} checks pass. Your footer and opt-out line are added.
        </p>
      )}
      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={busy} disabled={!checks?.ok || unfilled} icon={<Send className="h-4 w-4" />}>
          Send
        </Button>
        <SkipButton item={item} onDone={onDone} />
      </div>
    </form>
  );
}

function LinkedInStep({ item, blocked, onDone }: { item: OutreachQueueItem; blocked: string | null; onDone: () => void }) {
  const { busy, error, run } = useAction();
  const [note, setNote] = useState(item.draft.body);
  const [profile, setProfile] = useState(item.linkedin_is_search ? "" : (item.linkedin_url ?? ""));
  const [copied, setCopied] = useState(false);

  async function record(outcome: "sent" | "already_connected" | "wrong_person") {
    if (
      await run(() =>
        api(`/outreach/enrollments/${item.enrollment_id}/steps`, {
          method: "POST",
          body: { action: "linkedin", outcome, body: note, profile_url: profile.trim() || null },
        }).then(() => true),
      )
    )
      onDone();
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(note);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-[13px] text-fg-2">Send this in your own browser; VROS never touches LinkedIn. Then say how it went.</p>
      <Missing names={item.draft.missing} />
      <Field label="Connection note" hint={`${note.length} of 300 characters LinkedIn allows.`}>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} className={cx(inputClass, "resize-y")} />
      </Field>
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={copy} icon={<Copy className="h-4 w-4" />}>
          {copied ? "Copied" : "Copy note"}
        </Button>
        {item.linkedin_url && (
          <a
            href={item.linkedin_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-[13px] font-medium text-accent-text hover:underline"
          >
            {item.linkedin_is_search ? "Search for them on LinkedIn" : "Open their profile"}
            <ExternalLink aria-hidden className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
      <Field label="Their profile link (optional)" hint="Saved on the contact for next time.">
        <input value={profile} onChange={(e) => setProfile(e.target.value)} type="url" placeholder="https://www.linkedin.com/in/…" className={inputClass} />
      </Field>
      {blocked && <Note>{blocked}</Note>}
      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" busy={busy} disabled={!!blocked} onClick={() => record("sent")}>
          I sent it
        </Button>
        <Button busy={busy} onClick={() => record("already_connected")}>
          Already connected
        </Button>
        <Button busy={busy} onClick={() => record("wrong_person")}>
          Wrong person
        </Button>
        <SkipButton item={item} onDone={onDone} />
      </div>
    </div>
  );
}

function CallStep({ item, onDone }: { item: OutreachQueueItem; onDone: () => void }) {
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (
      await run(() =>
        api(`/outreach/enrollments/${item.enrollment_id}/steps`, {
          method: "POST",
          body: { action: "call", call_outcome: data.get("outcome"), note: String(data.get("note") ?? "").trim() || null },
        }).then(() => true),
      )
    )
      onDone();
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <p className="whitespace-pre-line text-[13px] text-fg-2">{item.draft.body}</p>
      <p className="text-[13px] text-fg">
        {item.contact_phone ? <>Phone: {item.contact_phone}</> : <span className="text-fg-3">No phone number on record.</span>}
      </p>
      <div className="grid gap-3 sm:grid-cols-[12rem_minmax(0,1fr)]">
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
        <Field label="Note (optional)">
          <input name="note" maxLength={2000} className={inputClass} />
        </Field>
      </div>
      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={busy} icon={<Phone className="h-4 w-4" />}>
          Log the call
        </Button>
        <SkipButton item={item} onDone={onDone} />
      </div>
    </form>
  );
}

function SkipButton({ item, onDone }: { item: OutreachQueueItem; onDone: () => void }) {
  const { busy, run } = useAction();
  return (
    <Button
      variant="ghost"
      busy={busy}
      icon={<SkipForward className="h-4 w-4" />}
      onClick={async () => {
        if (await run(() => api(`/outreach/enrollments/${item.enrollment_id}/steps`, { method: "POST", body: { action: "skip" } }).then(() => true))) onDone();
      }}
    >
      Skip
    </Button>
  );
}

/** One due step: who, why now, and the one thing to do. */
function QueueCard({ item, blocked, onDone }: { item: OutreachQueueItem; blocked: string | null; onDone: () => void }) {
  const channel = CHANNEL[item.channel];
  const Icon = channel.icon;
  // Someone who may not change records sees what is due, not the steps to do it.
  const writable = useCanChange();
  return (
    <article className="lift space-y-3 rounded-xl border border-border/80 bg-surface p-4" data-testid="queue-item">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-fg">
            {item.contact_name}
            {item.contact_title && <span className="font-normal text-fg-2"> · {item.contact_title}</span>}
          </p>
          <p className="text-xs text-fg-3">
            <Link href={`/accounts/${item.account_id}`} className="text-accent-text hover:underline">
              {item.account_name}
            </Link>{" "}
            · {item.sequence_name}, step {item.position + 1} of {item.total_steps}
            {item.due_at && ` · due ${formatDate(item.due_at)}`}
          </p>
        </div>
        <span className="flex items-center gap-1.5">
          <BandBadge band={item.priority_band} />
          <Badge tone="accent">
            <Icon aria-hidden className="h-3 w-3" />
            {channel.label}
          </Badge>
        </span>
      </header>
      {writable && item.channel === "email" && <EmailStep item={item} onDone={onDone} />}
      {writable && item.channel === "linkedin" && <LinkedInStep item={item} blocked={blocked} onDone={onDone} />}
      {writable && item.channel === "call" && <CallStep item={item} onDone={onDone} />}
    </article>
  );
}

/** Today's outreach: every due step, best prospects first. Nothing here happens without you. */
export function OutreachQueueView() {
  const { data, error, mutate } = useApi<OutreachQueue>("/outreach/queue");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={6} />;
  return (
    <div className="space-y-4" data-testid="outreach-queue">
      <p className="text-xs text-fg-3">
        LinkedIn today: {data.linkedin.today} of {data.linkedin.daily_limit} · this week: {data.linkedin.this_week} of {data.linkedin.weekly_limit}
      </p>
      {data.items.length === 0 ? (
        <Empty icon={<Send className="h-4 w-4" />}>Nothing due today. Enrol someone from an account&apos;s People to start a sequence.</Empty>
      ) : (
        data.items.map((item) => <QueueCard key={item.enrollment_id} item={item} blocked={data.linkedin.blocked} onDone={() => mutate()} />)
      )}
    </div>
  );
}
