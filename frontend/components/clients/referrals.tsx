"use client";

import { Handshake, Plus } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Badge, Button, Empty, ErrorNote, Field, inputClass, Panel, Skeleton, Table } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { formatDate, money } from "@/lib/format";
import { useAction, useApi, useCanChange } from "@/lib/hooks";
import type { Account360, Referral } from "@/lib/types";

const STATUSES: { key: Referral["status"]; label: string }[] = [
  { key: "received", label: "Received" },
  { key: "contacted", label: "Contacted" },
  { key: "declined", label: "Declined" },
];

function Revenue({ referral }: { referral: Referral }) {
  if (!referral.converted) return <span className="text-fg-3">None yet</span>;
  const known = referral.revenue.map((m) => money(m.amount, m.currency)).join(" + ");
  return (
    <span className="tabular text-fg">
      {known || "Value unknown"}
      {known && referral.unknown_value_deals > 0 && <span className="block text-xs text-fg-3">and {referral.unknown_value_deals} without a value</span>}
    </span>
  );
}

function StatusSelect({ referral }: { referral: Referral }) {
  const { busy, error, run } = useAction();
  const writable = useCanChange();
  return (
    <>
      <select
        aria-label={`Status of the referral of ${referral.referred_company}`}
        defaultValue={referral.status}
        disabled={busy || !writable}
        onChange={(e) => run(() => api(`/referrals/${referral.id}`, { method: "PATCH", body: { status: e.target.value } }))}
        className={cx(inputClass, "w-auto py-1 text-xs")}
      >
        {STATUSES.map((s) => (
          <option key={s.key} value={s.key}>
            {s.label}
          </option>
        ))}
      </select>
      <ErrorNote error={error} />
    </>
  );
}

/** Referrals: who referred whom, and whether a deal was won from it. */
export function ReferralTable({ referrals }: { referrals: Referral[] }) {
  return (
    <Table testId="referrals">
      <thead>
        <tr>
          <th>Referred company</th>
          <th>Referred by</th>
          <th>Received</th>
          <th>Status</th>
          <th>Converted</th>
          <th>Revenue</th>
        </tr>
      </thead>
      <tbody>
        {referrals.map((r) => (
          <tr key={r.id} data-testid="referral-row">
            <td className="min-w-[12rem]">
              {r.referred_account ? (
                <Link href={`/accounts/${r.referred_account.id}`} className="font-medium text-fg hover:text-accent-text hover:underline">
                  {r.referred_company}
                </Link>
              ) : (
                <span className="font-medium text-fg">{r.referred_company}</span>
              )}
              <span className="block text-xs text-fg-3">{r.referred_domain ?? "No website given"}</span>
            </td>
            <td className="min-w-[10rem] text-fg-2">
              {r.referrer_account ? (
                <Link href={`/accounts/${r.referrer_account.id}`} className="hover:underline">
                  {r.referrer_name}
                </Link>
              ) : (
                r.referrer_name
              )}
              {r.relationship && <span className="block text-xs text-fg-3">{r.relationship}</span>}
            </td>
            <td className="whitespace-nowrap text-fg-2">{formatDate(r.received_on)}</td>
            <td>
              <StatusSelect referral={r} />
            </td>
            <td>{r.converted ? <Badge tone="green">Won {r.won_deals === 1 ? "a deal" : `${r.won_deals} deals`}</Badge> : <Badge>Not yet</Badge>}</td>
            <td className="whitespace-nowrap">
              <Revenue referral={r} />
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

/** Log a referral. On an account it is that account (and one of its people) referring. */
export function ReferralForm({ account, onDone, onCancel }: { account?: Account360; onDone: () => void; onCancel: () => void }) {
  const { busy, error, run } = useAction();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const text = (key: string) => String(data.get(key) ?? "").trim() || null;
    const saved = await run(() =>
      api("/referrals", {
        method: "POST",
        body: {
          referrer_account_id: account?.id ?? null,
          referrer_contact_id: text("contact"),
          referrer_name: text("referrer"),
          relationship: text("relationship"),
          referred_company: text("company"),
          referred_domain: text("domain"),
          notes: text("notes"),
          received_on: text("on"),
        },
      }).then(() => true),
    );
    if (saved) onDone();
  }
  return (
    <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5" data-testid="referral-form">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Company they referred">
          <input name="company" required maxLength={300} className={inputClass} />
        </Field>
        <Field label="Its website (optional)" hint="Links the referral to the company once it is in VROS.">
          <input name="domain" maxLength={300} placeholder="example.com" className={inputClass} />
        </Field>
        {account ? (
          <Field label="Who referred them">
            <select name="contact" defaultValue="" className={inputClass}>
              <option value="">{account.name}</option>
              {account.contacts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.title ? `, ${c.title}` : ""}
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <Field label="Who referred them">
            <input name="referrer" required maxLength={200} placeholder="A name, and their company if any" className={inputClass} />
          </Field>
        )}
        <Field label="How they know Verkies (optional)">
          <input name="relationship" maxLength={120} placeholder="Client, partner, friend…" className={inputClass} />
        </Field>
        <Field label="When">
          <input name="on" type="date" className={inputClass} />
        </Field>
      </div>
      <Field label="Notes (optional)">
        <textarea name="notes" maxLength={4000} rows={2} className={cx(inputClass, "resize-y")} />
      </Field>
      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={busy}>
          Log referral
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Referrals this account gave, and the one that brought it in. */
export function AccountReferrals({ account }: { account: Account360 }) {
  const { data, error, mutate } = useApi<Referral[]>(`/referrals?account_id=${account.id}`);
  const [adding, setAdding] = useState(false);
  const writable = useCanChange();
  return (
    <Panel
      title="Referrals"
      description="Companies this account sent to Verkies, and who sent this one. Converted once a deal on the referred company is won."
      testId="account-referrals"
      actions={
        writable &&
        !adding && (
          <Button onClick={() => setAdding(true)} icon={<Plus className="h-4 w-4" />}>
            Log a referral they gave
          </Button>
        )
      }
    >
      <div className="space-y-4">
        {adding && (
          <ReferralForm
            account={account}
            onCancel={() => setAdding(false)}
            onDone={() => {
              setAdding(false);
              void mutate();
            }}
          />
        )}
        {error ? (
          <ErrorNote error={error} />
        ) : !data ? (
          <Skeleton rows={2} />
        ) : data.length === 0 ? (
          <Empty icon={<Handshake className="h-4 w-4" />}>No referrals yet.</Empty>
        ) : (
          <ReferralTable referrals={data} />
        )}
      </div>
    </Panel>
  );
}
