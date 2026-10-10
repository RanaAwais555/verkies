"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { BackLink } from "@/components/back";
import { AssessmentView, BriefView, EvidenceList } from "@/components/brief";
import { DecisionPanel } from "@/components/decision";
import {
  Badge,
  Button,
  PageHeader,
  Card,
  cx,
  ErrorNote,
  formatDate,
  label,
  Loading,
  SourceLink,
  StatusBadge,
  Tabs,
  TextLink,
} from "@/components/ui";
import { api } from "@/lib/client";
import { can, useApi, useSession, useTab } from "@/lib/hooks";
import type { Approval, Assessment, Brief, Intelligence, RunDetail } from "@/lib/types";
import { REJECTION_REASONS } from "@/lib/types";

const ACTIVE = new Set(["queued", "running", "retrying"]);

function Progress({ run }: { run: RunDetail }) {
  return (
    <Card title="Progress">
      <div className="mb-4 h-2 overflow-hidden rounded-full bg-surface" role="progressbar" aria-valuenow={run.progress_pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-2 rounded-full bg-accent transition-all" style={{ width: `${run.progress_pct}%` }} />
      </div>
      <ol className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-5" data-testid="stages">
        {run.stages.map((s) => (
          <li key={s.stage} className="flex items-center gap-2 text-sm">
            <span
              aria-hidden
              className={cx(
                "inline-block h-2 w-2 rounded-full",
                s.status === "completed" ? "bg-emerald-500" : s.status === "running" ? "animate-pulse bg-accent" : s.status === "failed" ? "bg-red-500" : "bg-border",
              )}
            />
            <span>{label(s.stage)}</span>
            <span className="text-xs text-muted">{s.status === "running" ? `${s.progress_pct}%` : s.status}</span>
          </li>
        ))}
      </ol>
      {run.error && <div className="mt-3"><ErrorNote error={new Error(run.error)} /></div>}
    </Card>
  );
}

function IntelligenceView({ runId }: { runId: string }) {
  const { data, error } = useApi<Intelligence>(`/research-runs/${runId}/intelligence`);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  return (
    <div className="space-y-4">
      {Object.entries(data.areas).map(([area, items]) => (
        <Card key={area} title={label(area)}>
          <ul className="space-y-2">
            {items.map((o) => (
              <li key={o.id} className="text-sm">
                <span className="font-mono text-xs text-muted">{o.key}</span>{" "}
                <span>{typeof o.value === "string" || typeof o.value === "number" || typeof o.value === "boolean" ? String(o.value) : JSON.stringify(o.value)}</span>
                <EvidenceList evidence={[o.evidence]} />
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

/** What was decided, and where to go next. `approval` is only known in the tab that approved. */
function Outcome({ run, approval, reviewer }: { run: RunDetail; approval: Approval | null; reviewer: boolean }) {
  const accountId = approval?.account_id ?? run.account_id;
  const approved = run.review_status === "approved";
  return (
    <Card className={approved ? "border-emerald-300 dark:border-emerald-900" : "border-red-300 dark:border-red-900"}>
      {run.review_status === "approved" ? (
        <div className="space-y-1 text-sm" data-testid="approved">
          <p>
            <strong>Approved</strong> {formatDate(run.reviewed_at, true)}.
            {approval && (
              <>
                {" "}{approval.created_account ? "New account created" : "Added to the existing account"} with a lead,
                {approval.opportunity_id ? " an opportunity," : ""} {approval.contact_ids.length} contact
                {approval.contact_ids.length === 1 ? "" : "s"} and a task due {formatDate(approval.task_due_at)}.
              </>
            )}
          </p>
        </div>
      ) : (
        <p className="text-sm" data-testid="rejected">
          <strong>Rejected:</strong> {REJECTION_REASONS[run.rejection_reason ?? ""] ?? run.rejection_reason}
          {run.rejection_note && ` — ${run.rejection_note}`} ({formatDate(run.reviewed_at, true)}). It is off the review
          queue and stays searchable under Research.
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {run.review_status === "approved" && accountId && (
          <Link href={`/accounts/${accountId}`} className="rounded-lg bg-accent px-3.5 py-2 text-sm font-medium text-accent-foreground shadow-sm hover:bg-accent-hover">
            Open the account
          </Link>
        )}
        {reviewer && (
          <Link href="/" className="rounded-lg border border-border bg-background px-3.5 py-2 text-sm font-medium shadow-sm hover:bg-surface">
            Back to the review queue
          </Link>
        )}
      </div>
    </Card>
  );
}

function PagesView({ run }: { run: RunDetail }) {
  return (
    <Card title={`Pages (${run.pages.length})`}>
      <ul className="space-y-1 text-sm">
        {run.pages.map((p) => (
          <li key={`${p.kind}-${p.url}`} className="flex flex-wrap items-center gap-2">
            <Badge>{p.kind === "page" ? p.category ?? "page" : p.kind}</Badge>
            <SourceLink url={p.url} />
            <span className="text-xs text-muted">
              {p.status_code ?? "—"}{p.rendered ? " · rendered" : ""}{p.from_cache ? " · cached" : ""}
              {p.skip_reason ? ` · skipped: ${p.skip_reason}` : ""}{p.error ? ` · ${p.error}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function ResearchRunPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session } = useSession();
  const { data: run, error, mutate } = useApi<RunDetail>(`/research-runs/${id}`, {
    refreshInterval: (latest) => (latest && !ACTIVE.has(latest.status) ? 0 : 1500),
  });
  const completed = run?.status === "completed";
  const { data: brief, mutate: refreshBrief } = useApi<Brief>(completed ? `/research-runs/${id}/brief` : null);
  const { data: assessment } = useApi<Assessment>(completed ? `/research-runs/${id}/assessment` : null);
  const [tab, setTab] = useTab("brief");
  const [approval, setApproval] = useState<Approval | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  async function act(action: "cancel" | "retry") {
    setBusy(true);
    setActionError(null);
    try {
      await api(`/research-runs/${id}/${action}`, { method: "POST" });
      await mutate();
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  const back = <BackLink fallback="/research" />;
  if (error) return <div className="space-y-4">{back}<ErrorNote error={error} /></div>;
  if (!run || !session) return <div className="space-y-4">{back}<Loading /></div>;

  const nextAction = brief?.sections.next_action?.claims[0]?.text ?? null;
  const needsOverride = !!assessment && (!assessment.score?.qualifies || !!assessment.qualification?.hard_reject);
  const reviewer = can(session, "prospects.review");
  const reviewable = completed && run.review_status === "pending" && reviewer && brief && assessment;

  return (
    <div className="space-y-5">
      <PageHeader
        back={back}
        title={run.normalised_domain}
        badges={
          <>
            <StatusBadge status={run.status} />
            <StatusBadge status={run.review_status} />
          </>
        }
        description={
          <>
            <SourceLink url={run.input_url} /> · started {formatDate(run.created_at, true)}
            {run.retry_count > 0 && ` · attempt ${run.retry_count + 1}`}
          </>
        }
        actions={
          <>
            {run.account_id && run.review_status !== "approved" && <TextLink href={`/accounts/${run.account_id}`}>Open account</TextLink>}
            {ACTIVE.has(run.status) && <Button variant="secondary" busy={busy} onClick={() => act("cancel")}>Cancel</Button>}
            {(run.status === "failed" || run.status === "cancelled") && <Button variant="secondary" busy={busy} onClick={() => act("retry")}>Retry</Button>}
          </>
        }
      />
      <ErrorNote error={actionError} />
      {run.review_status !== "pending" && <Outcome run={run} approval={approval} reviewer={reviewer} />}
      {!completed && <Progress run={run} />}
      {reviewable && (
        <DecisionPanel
          runId={id}
          session={session}
          nextAction={nextAction}
          needsOverride={needsOverride}
          recommendedRejection={assessment.qualification?.rejection_reason ?? null}
          onDecided={async (decided) => {
            if (decided) setApproval(decided);
            await Promise.all([mutate(), refreshBrief()]);
          }}
        />
      )}
      {completed && (
        <>
          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { key: "brief", label: "Lead brief" },
              { key: "assessment", label: "Opportunities and scores" },
              { key: "intelligence", label: "Intelligence" },
              { key: "pages", label: "Pages crawled" },
            ]}
          />
          {tab === "brief" && (brief ? <BriefView brief={brief} /> : <Loading />)}
          {tab === "assessment" && (assessment ? <AssessmentView assessment={assessment} /> : <Loading />)}
          {tab === "intelligence" && <IntelligenceView runId={id} />}
          {tab === "pages" && <PagesView run={run} />}
        </>
      )}
      {!completed && run.pages.length > 0 && <PagesView run={run} />}
    </div>
  );
}
