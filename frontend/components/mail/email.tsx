"use client";

import { AlertTriangle, CheckCircle2, CircleX, Mail, MailOpen, Send, Undo2 } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Badge, Button, Empty, ErrorNote, Field, inputClass, Skeleton } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { formatDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Contact, Email, EmailPreflight } from "@/lib/types";

/**
 * Write one email to one person. The checks run first and the Send button stays off until every
 * one passes; VROS adds the footer with your name, the company and the opt-out line.
 */
export function EmailComposer({
  contact,
  dealId,
  replyTo,
  onSent,
  onCancel,
}: {
  contact: Pick<Contact, "id" | "name">;
  dealId?: string;
  replyTo?: Email;
  onSent?: () => void;
  onCancel?: () => void;
}) {
  const { data: checks, error } = useApi<EmailPreflight>(`/email/preflight?contact_id=${contact.id}`);
  const { busy, error: sendError, run } = useAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const sent = await run(() =>
      api("/email/send", {
        method: "POST",
        body: {
          contact_id: contact.id,
          subject: String(data.get("subject") ?? "").trim(),
          body: String(data.get("body") ?? ""),
          deal_id: dealId ?? replyTo?.deal_id ?? null,
          opportunity_id: replyTo?.opportunity_id ?? null,
          reply_to_id: replyTo?.id ?? null,
        },
      }).then(() => true),
    );
    if (sent) onSent?.();
  }

  const failing = checks?.checks.filter((c) => !c.ok) ?? [];
  return (
    <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5" data-testid="email-composer">
      <p className="text-[13px] text-fg-2">
        To <span className="font-medium text-fg">{contact.name}</span>
        {checks?.recipient && <span className="text-fg-3"> &lt;{checks.recipient}&gt;</span>}
        {checks?.sender && <span className="text-fg-3"> · from {checks.sender}</span>}
      </p>
      {error && <ErrorNote error={error} />}
      {!checks && !error && <Skeleton rows={2} />}
      {checks && (
        <ul className="space-y-1" aria-label="Checks before sending" data-testid="email-checks">
          {(failing.length ? failing : checks.checks).map((c) => (
            <li key={c.key} className={cx("flex items-start gap-1.5 text-xs", c.ok ? "text-fg-3" : "text-bad")}>
              {c.ok ? (
                <CheckCircle2 aria-hidden className="mt-px h-3.5 w-3.5 shrink-0 text-ok" />
              ) : (
                <CircleX aria-hidden className="mt-px h-3.5 w-3.5 shrink-0" />
              )}
              {c.message}
            </li>
          ))}
          {failing.length > 0 && (
            <li className="text-xs text-fg-3">
              {checks.checks.length - failing.length} of {checks.checks.length} checks pass.{" "}
              <Link href="/settings?tab=mailbox" className="text-accent-text hover:underline">
                Mailbox settings
              </Link>
            </li>
          )}
        </ul>
      )}
      <Field label="Subject">
        <input
          name="subject"
          required
          maxLength={300}
          defaultValue={replyTo ? (replyTo.subject.startsWith("Re:") ? replyTo.subject : `Re: ${replyTo.subject}`) : ""}
          className={inputClass}
        />
      </Field>
      <Field label="Message" hint="Plain text. Short, one clear ask.">
        <textarea name="body" required maxLength={20000} rows={6} className={cx(inputClass, "resize-y leading-relaxed")} />
      </Field>
      {checks && <pre className="whitespace-pre-wrap rounded-lg bg-sunken p-2.5 font-sans text-xs text-fg-3">{checks.footer}</pre>}
      <ErrorNote error={sendError} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={busy} disabled={!checks?.ok} icon={<Send className="h-4 w-4" />}>
          Send
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

const STATUS_TONE = { sent: "accent", received: "green", failed: "red", bounced: "red" } as const;

/** Emails on an account (or a contact or deal), newest first, each expandable to its text. */
export function EmailList({ query, empty = "No email yet." }: { query: string; empty?: string }) {
  const { data, error } = useApi<Email[]>(`/email/messages?${query}`);
  const [open, setOpen] = useState<string | null>(null);
  const [replying, setReplying] = useState<string | null>(null);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={3} />;
  if (data.length === 0) return <Empty icon={<Mail className="h-4 w-4" />}>{empty}</Empty>;
  return (
    <ul className="divide-y divide-grid" data-testid="emails">
      {data.map((m) => {
        const inbound = m.direction === "inbound";
        const Icon = inbound ? MailOpen : Mail;
        return (
          <li key={m.id} className="py-3 first:pt-0 last:pb-0" data-testid="email">
            <button
              type="button"
              onClick={() => setOpen(open === m.id ? null : m.id)}
              aria-expanded={open === m.id}
              className="flex w-full items-start gap-3 text-left"
            >
              <Icon aria-hidden className={cx("mt-0.5 h-4 w-4 shrink-0", inbound ? "text-ok" : "text-accent-text")} />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="truncate font-medium text-fg">{m.subject || "(no subject)"}</span>
                  <Badge tone={STATUS_TONE[m.status]}>{m.status}</Badge>
                  {m.classification === "opt_out" && <Badge tone="amber">Opted out</Badge>}
                </span>
                <span className="block text-xs text-fg-3">
                  {inbound ? `From ${m.contact_name ?? m.from_address}` : `To ${m.contact_name ?? m.to_address}`} · {formatDate(m.occurred_at, true)}
                </span>
              </span>
            </button>
            {open === m.id && (
              <div className="ml-7 mt-2 space-y-2">
                {m.error && (
                  <p className="flex items-center gap-1.5 text-xs text-bad">
                    <AlertTriangle aria-hidden className="h-3.5 w-3.5" />
                    {m.error}
                  </p>
                )}
                <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-fg-2">{m.body_text}</pre>
                {inbound &&
                  m.contact_id &&
                  m.classification !== "opt_out" &&
                  (replying === m.id ? (
                    <EmailComposer
                      contact={{ id: m.contact_id, name: m.contact_name ?? m.from_address }}
                      replyTo={m}
                      onSent={() => setReplying(null)}
                      onCancel={() => setReplying(null)}
                    />
                  ) : (
                    <Button className="h-7 px-2.5 text-xs" icon={<Undo2 className="h-3.5 w-3.5" />} onClick={() => setReplying(m.id)}>
                      Reply
                    </Button>
                  ))}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
