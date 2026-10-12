"use client";

import { Check, Lightbulb, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Badge, Button, Empty, ErrorNote, Field, inputClass, Panel, Skeleton, Success, Table, type Tone } from "@/components/ui";
import { api, ApiError } from "@/lib/client";
import { formatDate } from "@/lib/format";
import { can, useAction, useApi, useSession } from "@/lib/hooks";
import type { LearnedProposal } from "@/lib/types";

const STATUS: Record<LearnedProposal["status"], { label: string; tone: Tone }> = {
  proposed: { label: "Waiting for a decision", tone: "amber" },
  activated: { label: "Activated", tone: "green" },
  dismissed: { label: "Dismissed", tone: "neutral" },
  superseded: { label: "Replaced by a newer proposal", tone: "neutral" },
};

const TIERS: Record<string, string> = { S: "Tier S", A: "Tier A", B: "Tier B", other: "Not in a tier" };

function shown(kind: LearnedProposal["kind"], value: number | string) {
  if (kind === "icp") return TIERS[String(value)] ?? String(value);
  return `${Math.round(Number(value) * 100)}%`;
}

function Decide({ proposal }: { proposal: LearnedProposal }) {
  const { busy, error, run } = useAction();
  const [dismissing, setDismissing] = useState(false);

  async function dismiss(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
    await run(() => api(`/learning/proposals/${proposal.id}/dismiss`, { method: "POST", body: { reason } }));
  }

  return (
    <div className="space-y-2">
      {dismissing ? (
        <form onSubmit={dismiss} className="flex flex-wrap items-end gap-2">
          <Field label="Why not" className="min-w-0 flex-1">
            <input name="reason" required minLength={3} maxLength={500} className={inputClass} />
          </Field>
          <Button type="submit" busy={busy}>
            Dismiss
          </Button>
          <Button variant="ghost" onClick={() => setDismissing(false)}>
            Cancel
          </Button>
        </form>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            busy={busy}
            icon={<Check className="h-4 w-4" />}
            onClick={() => run(() => api(`/learning/proposals/${proposal.id}/activate`, { method: "POST", body: {} }))}
          >
            Activate as version {proposal.based_on_version + 1}
          </Button>
          <Button variant="ghost" icon={<X className="h-4 w-4" />} onClick={() => setDismissing(true)}>
            Dismiss
          </Button>
        </div>
      )}
      <ErrorNote error={error} />
    </div>
  );
}

function ProposalCard({ proposal, manage }: { proposal: LearnedProposal; manage: boolean }) {
  const status = STATUS[proposal.status];
  const what = proposal.kind === "scoring" ? "Scoring weights" : "ICP industry tiers";
  return (
    <Panel
      title={what}
      description={`From ${proposal.basis.outcomes} closed deals (${proposal.basis.won} won, ${proposal.basis.lost} lost), against version ${proposal.based_on_version}. Made ${formatDate(proposal.created_at)}${proposal.created_by ? ` by ${proposal.created_by}` : ""}.`}
      actions={<Badge tone={status.tone}>{status.label}</Badge>}
      testId="proposal"
    >
      <div className="space-y-4">
        {/* The table pulls the next element up when it is not last in its card; the padding gives that back. */}
        <div className="pb-4">
          <Table>
            <thead>
              <tr>
                <th>{proposal.kind === "scoring" ? "Dimension" : "Industry"}</th>
                <th>Now</th>
                <th>Proposed</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {proposal.changes.map((c) => (
                <tr key={c.key} data-testid="proposal-change">
                  <td className="whitespace-nowrap font-medium text-fg">{c.label}</td>
                  <td className="tabular whitespace-nowrap text-fg-2">{shown(proposal.kind, c.from)}</td>
                  <td className="tabular whitespace-nowrap font-medium text-fg">{shown(proposal.kind, c.to)}</td>
                  <td className="min-w-[18rem] text-xs text-fg-2">{c.why}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
        {proposal.status === "proposed" && manage && <Decide proposal={proposal} />}
        {proposal.status === "activated" && (
          <p className="text-xs text-fg-3">
            Activated as version {proposal.activated_version} by {proposal.decided_by ?? "someone"} on {formatDate(proposal.decided_at)}. It can be changed at
            any time in Settings.
          </p>
        )}
        {proposal.status === "dismissed" && (
          <p className="text-xs text-fg-3">
            Dismissed by {proposal.decided_by ?? "someone"}: {proposal.decision_note}
          </p>
        )}
      </div>
    </Panel>
  );
}

/** §15 learning: proposals worked out from outcomes. Nothing changes until a person activates one. */
export function Proposals() {
  const { data: session } = useSession();
  const manage = can(session, "config.manage");
  const { data, error } = useApi<LearnedProposal[]>("/learning/proposals");
  const { busy, error: proposeError, run } = useAction();
  const [made, setMade] = useState<string | null>(null);

  async function propose(kind: LearnedProposal["kind"]) {
    setMade(null);
    const done = await run(() => api<LearnedProposal>("/learning/proposals", { method: "POST", body: { kind } }));
    if (done) setMade(`${done.changes.length} change${done.changes.length === 1 ? "" : "s"} proposed. Review it below; nothing is active yet.`);
  }

  const quiet = proposeError instanceof ApiError && proposeError.code === "no_change";
  return (
    <div className="space-y-4">
      <Panel
        title="Learn from outcomes"
        description="VROS compares what won and lost deals looked like and proposes small changes: no weight moves by more than a quarter, an industry moves one tier at most, and nothing is proposed from fewer than the minimum number of won and lost deals. A proposal stays inactive until an admin activates it."
      >
        {manage ? (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Button busy={busy} icon={<Lightbulb className="h-4 w-4" />} onClick={() => propose("scoring")}>
                Propose scoring weights
              </Button>
              <Button busy={busy} icon={<Lightbulb className="h-4 w-4" />} onClick={() => propose("icp")}>
                Propose ICP industry tiers
              </Button>
            </div>
            {made && <Success>{made}</Success>}
            {quiet ? <Success>The outcomes support the current configuration: nothing to change.</Success> : <ErrorNote error={proposeError} />}
          </div>
        ) : (
          <p className="text-[13px] text-fg-3">Admins make and activate proposals. You can see them here.</p>
        )}
      </Panel>
      {error ? (
        <ErrorNote error={error} />
      ) : !data ? (
        <Skeleton rows={4} />
      ) : data.length === 0 ? (
        <Panel>
          <Empty icon={<Lightbulb className="h-4 w-4" />}>No proposals yet.</Empty>
        </Panel>
      ) : (
        data.map((p) => <ProposalCard key={p.id} proposal={p} manage={manage} />)
      )}
    </div>
  );
}
