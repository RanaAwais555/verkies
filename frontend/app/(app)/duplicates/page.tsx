"use client";

import { Check, GitMerge, X } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Badge, BandBadge, Button, Empty, ErrorNote, Field, inputClass, PageHeader, Panel, ScoreChip, Skeleton, Success } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { formatDate, initials, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { AccountSummary, DuplicatePair, MergeResult } from "@/lib/types";

const pairKey = (p: DuplicatePair) => `${p.account_a.id}:${p.account_b.id}`;

function Side({ account, keep, onKeep }: { account: AccountSummary; keep: boolean; onKeep: () => void }) {
  return (
    <div
      className={cx(
        "min-w-0 space-y-2 rounded-xl border p-4 transition-colors duration-200 ease-spring",
        keep ? "border-accent/60 bg-accent-soft/40" : "border-border bg-surface-2",
      )}
    >
      <div className="flex items-start gap-3">
        <span aria-hidden className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-sm font-semibold text-accent-text">
          {initials(account.name)}
        </span>
        <div className="min-w-0">
          <Link href={`/accounts/${account.id}`} className="font-semibold text-fg hover:text-accent-text">
            {account.name}
          </Link>
          <p className="truncate text-xs text-fg-3">{account.primary_domain ?? "No website"}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <ScoreChip value={account.priority_score} />
        <BandBadge band={account.priority_band} />
        <Badge>{label(account.account_type)}</Badge>
      </div>
      <p className="text-xs text-fg-3">
        Owner: {account.owner?.name ?? "unassigned"} · {account.open_tasks} open tasks · added {formatDate(account.created_at)}
      </p>
      <Button onClick={onKeep} variant={keep ? "primary" : "secondary"} icon={keep ? <Check className="h-4 w-4" /> : undefined} className="h-8 text-xs">
        {keep ? "Keeping this one" : "Keep this one"}
      </Button>
    </div>
  );
}

function PairCard({ pair, onDone }: { pair: DuplicatePair; onDone: (message: string) => void }) {
  const [keep, setKeep] = useState<"a" | "b" | null>(null);
  const merge = useAction();
  const dismiss = useAction();
  const kept = keep === "a" ? pair.account_a : pair.account_b;
  const retired = keep === "a" ? pair.account_b : pair.account_a;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
    const result = await merge.run(() =>
      api<MergeResult>(`/accounts/${kept.id}/merge`, { method: "POST", body: { merge_id: retired.id, reason } }),
    );
    if (result) {
      const moved = Object.values(result.moved).reduce((sum, n) => sum + n, 0);
      onDone(`${retired.name} merged into ${kept.name}: ${moved} records moved${result.filled.length ? `, ${result.filled.length} empty fields filled` : ""}.`);
    }
  }

  async function different() {
    const done = await dismiss.run(() =>
      api("/account-duplicates/dismiss", { method: "POST", body: { account_a_id: pair.account_a.id, account_b_id: pair.account_b.id } }).then(() => true),
    );
    if (done) onDone(`${pair.account_a.name} and ${pair.account_b.name} marked as different companies.`);
  }

  return (
    <Panel
      title={pair.reasons.join(" · ")}
      actions={
        <Button variant="ghost" busy={dismiss.busy} onClick={different} icon={<X className="h-4 w-4" />}>
          Not duplicates
        </Button>
      }
      testId="duplicate"
    >
      <div className="grid gap-3 md:grid-cols-2">
        <Side account={pair.account_a} keep={keep === "a"} onKeep={() => setKeep("a")} />
        <Side account={pair.account_b} keep={keep === "b"} onKeep={() => setKeep("b")} />
      </div>
      <ErrorNote error={dismiss.error} />
      {keep && (
        <form onSubmit={submit} className="animate-rise mt-4 space-y-3 rounded-xl border border-border bg-surface-2 p-4">
          <p className="text-[13px] text-fg-2">
            <strong className="text-fg">{retired.name}</strong> will be retired. Its contacts, leads, opportunities, tasks, research and domains move to{" "}
            <strong className="text-fg">{kept.name}</strong>, which also takes any details it is missing. Its history stays readable from {kept.name}. This is
            audited.
          </p>
          <Field label="Why are these the same company?">
            <input name="reason" required minLength={3} maxLength={500} placeholder="e.g. Same company number on both websites" className={inputClass} />
          </Field>
          <ErrorNote error={merge.error} />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="primary" busy={merge.busy} icon={<GitMerge className="h-4 w-4" />}>
              Merge into {kept.name}
            </Button>
            <Button variant="ghost" onClick={() => setKeep(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Panel>
  );
}

export default function DuplicatesPage() {
  const { data, error, mutate } = useApi<DuplicatePair[]>("/account-duplicates");
  const [done, setDone] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Management"
        title="Duplicates"
        description="Accounts that look like the same company. Nothing is merged unless you choose to; every merge is audited."
      />
      {done && <Success testId="duplicate-result">{done}</Success>}
      {error && <ErrorNote error={error} />}
      {!data && !error && <Skeleton rows={6} />}
      {data?.length === 0 && (
        <Panel>
          <Empty>No possible duplicates. Similar names, the same legal name or the same website name would show here.</Empty>
        </Panel>
      )}
      {data?.map((pair) => (
        <PairCard
          key={pairKey(pair)}
          pair={pair}
          onDone={(message) => {
            setDone(message);
            mutate();
          }}
        />
      ))}
    </div>
  );
}
