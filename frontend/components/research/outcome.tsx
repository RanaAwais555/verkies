import { ArrowRight, CircleCheck, CircleX } from "lucide-react";

import { LinkButton, Panel } from "@/components/ui";
import { formatDate } from "@/lib/format";
import type { Approval, RunDetail } from "@/lib/types";
import { REJECTION_REASONS } from "@/lib/types";

/** What was decided and where to go next. `approval` is only known in the tab that approved. */
export function Outcome({ run, approval, reviewer }: { run: RunDetail; approval: Approval | null; reviewer: boolean }) {
  const accountId = approval?.account_id ?? run.account_id;
  const approved = run.review_status === "approved";
  return (
    <Panel primary className={approved ? "border-ok/40" : "border-bad/40"}>
      <div className="flex gap-3">
        {approved ? <CircleCheck aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-ok" /> : <CircleX aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-bad" />}
        <div className="min-w-0 flex-1 space-y-3">
          {approved ? (
            <p className="text-[13.5px] text-fg" data-testid="approved">
              <strong className="font-semibold">Approved</strong> {formatDate(run.reviewed_at, true)}.
              {approval && (
                <>
                  {" "}
                  {approval.created_account ? "New account created" : "Added to the existing account"} with a lead,
                  {approval.opportunity_id ? " an opportunity," : ""} {approval.contact_ids.length} contact
                  {approval.contact_ids.length === 1 ? "" : "s"} and a task due {formatDate(approval.task_due_at)}.
                </>
              )}
            </p>
          ) : (
            <p className="text-[13.5px] text-fg" data-testid="rejected">
              <strong className="font-semibold">Rejected:</strong> {REJECTION_REASONS[run.rejection_reason ?? ""] ?? run.rejection_reason}
              {run.rejection_note && ` — ${run.rejection_note}`} ({formatDate(run.reviewed_at, true)}). It is off the review queue and stays searchable
              under Lead Intelligence.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {approved && accountId && (
              <LinkButton href={`/accounts/${accountId}`} variant="primary" icon={<ArrowRight className="h-4 w-4" />}>
                Open the account
              </LinkButton>
            )}
            {reviewer && <LinkButton href="/">Back to the review queue</LinkButton>}
          </div>
        </div>
      </div>
    </Panel>
  );
}
