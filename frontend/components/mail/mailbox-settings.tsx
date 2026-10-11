"use client";

import { CheckCircle2, CircleAlert, CircleHelp, Inbox, Mail, RefreshCw, Unplug } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Badge, Button, Checkbox, ErrorNote, Field, inputClass, Note, Panel, Skeleton, Success } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { formatDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { DnsCheck, Mailbox, MailboxState } from "@/lib/types";

const DNS_LABELS: { key: "mx" | "spf" | "dkim" | "dmarc"; label: string }[] = [
  { key: "mx", label: "MX (can receive replies)" },
  { key: "spf", label: "SPF (who may send for your domain)" },
  { key: "dkim", label: "DKIM (signs your email)" },
  { key: "dmarc", label: "DMARC (tells receivers what to do)" },
];

const STATUS: Record<Mailbox["status"], { label: string; tone: "green" | "red" | "amber" | "neutral" }> = {
  connected: { label: "Connected", tone: "green" },
  failing: { label: "Cannot sign in", tone: "red" },
  unverified: { label: "Not checked", tone: "amber" },
  disconnected: { label: "Disconnected", tone: "neutral" },
};

function DnsRow({ label, check }: { label: string; check?: DnsCheck }) {
  const status = check?.status ?? "unknown";
  const Icon = status === "pass" ? CheckCircle2 : status === "fail" ? CircleAlert : CircleHelp;
  return (
    <li className="flex gap-2.5 py-2 text-[13px]">
      <Icon aria-hidden className={cx("mt-0.5 h-4 w-4 shrink-0", status === "pass" ? "text-ok" : status === "fail" ? "text-bad" : "text-fg-3")} />
      <div className="min-w-0">
        <p className="text-fg">
          {label} <span className="sr-only">: {status}</span>
        </p>
        {check?.record && <p className="truncate font-mono text-[11.5px] text-fg-3">{check.record}</p>}
        {check?.advice && <p className="text-xs text-fg-2">{check.advice}</p>}
      </div>
    </li>
  );
}

/**
 * Connect your own mailbox over IMAP and SMTP. The password is encrypted at rest and never shown
 * again. Sending needs all of: the admin's switch, this mailbox's switch, and passing DNS checks.
 */
export function MailboxSettings() {
  const { data, error, mutate } = useApi<MailboxState>("/mailbox");
  const save = useAction();
  const action = useAction();
  const [synced, setSynced] = useState<string | null>(null);

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Skeleton rows={6} />;
  const box = data.mailbox;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const text = (name: string) => String(form.get(name) ?? "").trim();
    const password = String(form.get("password") ?? "");
    const ok = await save.run(() =>
      api("/mailbox", {
        method: "PUT",
        body: {
          address: text("address"),
          display_name: text("display_name"),
          smtp_host: text("smtp_host"),
          smtp_port: Number(text("smtp_port")),
          smtp_security: text("smtp_security"),
          imap_host: text("imap_host"),
          imap_port: Number(text("imap_port")),
          username: text("username") || text("address"),
          password: password || null,
          dkim_selector: text("dkim_selector") || null,
          daily_cap: Number(text("daily_cap")) || 20,
          sending_enabled: form.get("sending_enabled") === "on",
        },
      }).then(() => true),
    );
    if (ok) await mutate();
  }

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Panel
        title="Your mailbox"
        description="Emails you send from VROS go out from your own address, and replies from your contacts come back to the account timeline. Nobody else uses your mailbox."
        actions={box && <Badge tone={STATUS[box.status].tone}>{STATUS[box.status].label}</Badge>}
        testId="mailbox"
      >
        {!data.sending_allowed_by_admin && (
          <Note>Sending is switched off for VROS. You can connect and check your mailbox; an admin turns sending on with VROS_EMAIL_SENDING_ENABLED.</Note>
        )}
        {box?.last_error && <p className="mb-3 text-[13px] text-bad">{box.last_error}</p>}
        <form key={box ? `${box.address}${box.status}` : "new"} onSubmit={submit} className="space-y-3" data-testid="mailbox-form">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Email address">
              <input name="address" type="email" required defaultValue={box?.address ?? ""} className={inputClass} />
            </Field>
            <Field label="Name on your emails">
              <input name="display_name" required maxLength={200} defaultValue={box?.display_name ?? ""} className={inputClass} />
            </Field>
            <Field label="SMTP server" hint="For sending, e.g. smtp.gmail.com">
              <input name="smtp_host" required defaultValue={box?.smtp_host ?? ""} className={inputClass} />
            </Field>
            <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-2">
              <Field label="SMTP port">
                <input name="smtp_port" type="number" min={1} max={65535} required defaultValue={box?.smtp_port ?? 465} className={inputClass} />
              </Field>
              <Field label="Security">
                <select name="smtp_security" defaultValue={box?.smtp_security ?? "ssl"} className={inputClass}>
                  <option value="ssl">SSL/TLS</option>
                  <option value="starttls">STARTTLS</option>
                </select>
              </Field>
            </div>
            <Field label="IMAP server" hint="For reading replies, e.g. imap.gmail.com">
              <input name="imap_host" required defaultValue={box?.imap_host ?? ""} className={inputClass} />
            </Field>
            <Field label="IMAP port">
              <input name="imap_port" type="number" min={1} max={65535} required defaultValue={box?.imap_port ?? 993} className={inputClass} />
            </Field>
            <Field label="Sign-in name" hint="Usually your email address.">
              <input name="username" defaultValue={box?.username ?? ""} className={inputClass} />
            </Field>
            <Field label="Password" hint={box?.has_password ? "Stored encrypted. Leave empty to keep it." : "An app password if your provider offers one."}>
              <input name="password" type="password" autoComplete="new-password" required={!box?.has_password} className={inputClass} />
            </Field>
            <Field label="DKIM selector" hint="From your mail provider, e.g. google or selector1.">
              <input name="dkim_selector" maxLength={63} defaultValue={box?.dkim_selector ?? ""} className={inputClass} />
            </Field>
            <Field label="Daily limit" hint="Start low; raise it as the mailbox warms up.">
              <input name="daily_cap" type="number" min={1} max={500} defaultValue={box?.daily_cap ?? 20} className={inputClass} />
            </Field>
          </div>
          <Checkbox
            name="sending_enabled"
            defaultChecked={box?.sending_enabled ?? false}
            label="Allow sending from this mailbox (each email still needs you to click Send)"
          />
          <ErrorNote error={save.error} />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="primary" busy={save.busy} icon={<Mail className="h-4 w-4" />}>
              {box ? "Save and check" : "Connect and check"}
            </Button>
            {box && box.status !== "disconnected" && (
              <Button
                variant="ghost"
                icon={<Unplug className="h-4 w-4" />}
                onClick={async () => {
                  if (await action.run(() => api("/mailbox", { method: "DELETE" }).then(() => true))) await mutate();
                }}
              >
                Disconnect
              </Button>
            )}
          </div>
        </form>
      </Panel>

      <div className="flex min-w-0 flex-col gap-4">
        <Panel
          title="Sending checks"
          description={
            box?.dns_checked_at
              ? `Your domain's DNS, checked ${formatDate(box.dns_checked_at, true)}. Sending needs all four.`
              : "Your domain's DNS is checked when you connect."
          }
          actions={
            box && (
              <Button
                busy={action.busy}
                icon={<RefreshCw className="h-4 w-4" />}
                onClick={async () => {
                  if (await action.run(() => api("/mailbox/check", { method: "POST" }).then(() => true))) await mutate();
                }}
              >
                Check again
              </Button>
            )
          }
          testId="dns-checks"
        >
          {box ? (
            <ul className="divide-y divide-grid">
              {DNS_LABELS.map((d) => (
                <DnsRow key={d.key} label={d.label} check={box.dns_checks[d.key]} />
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-fg-3">Connect a mailbox to see what to fix before sending.</p>
          )}
        </Panel>
        {box && box.status !== "disconnected" && (
          <Panel
            title="Replies"
            description={
              box.last_synced_at
                ? `Last checked ${formatDate(box.last_synced_at, true)}.`
                : "Not checked yet. VROS reads only mail from your contacts, or replies to emails you sent from VROS."
            }
          >
            <Button
              busy={action.busy}
              icon={<Inbox className="h-4 w-4" />}
              onClick={async () => {
                const result = await action.run(() =>
                  api<{ read: number; stored: number; opt_outs: number; bounces: number }>("/mailbox/sync", { method: "POST" }),
                );
                if (result) {
                  setSynced(
                    `${result.stored} ${result.stored === 1 ? "email" : "emails"} added to accounts` +
                      (result.opt_outs ? `, ${result.opt_outs} opt-out${result.opt_outs === 1 ? "" : "s"}` : "") +
                      (result.bounces ? `, ${result.bounces} bounce${result.bounces === 1 ? "" : "s"}` : "") +
                      ".",
                  );
                  await mutate();
                }
              }}
            >
              Check for replies
            </Button>
            {synced && <Success>{synced}</Success>}
          </Panel>
        )}
        <ErrorNote error={action.error} />
      </div>
    </div>
  );
}
