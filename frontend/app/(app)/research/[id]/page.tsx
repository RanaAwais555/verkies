"use client";

import { Globe, RotateCcw, Square } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";

import { AssessmentView } from "@/components/research/assessment";
import { BriefView } from "@/components/research/brief";
import { DecisionPanel } from "@/components/research/decision";
import { IntelligenceView } from "@/components/research/intelligence";
import { Outcome } from "@/components/research/outcome";
import { PagesView } from "@/components/research/pages";
import { Progress } from "@/components/research/progress";
import { Button, ErrorNote, ProfileCard, Skeleton, SourceLink, StatusBadge, Tabs, TextLink } from "@/components/ui";
import { api } from "@/lib/client";
import { formatDate } from "@/lib/format";
import { can, useAction, useApi, useSession, useTab } from "@/lib/hooks";
import type { Approval, Assessment, Brief, RunDetail } from "@/lib/types";

const ACTIVE = new Set(["queued", "running", "retrying"]);

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
  const action = useAction();

  async function act(kind: "cancel" | "retry") {
    if (await action.run(() => api(`/research-runs/${id}/${kind}`, { method: "POST" }).then(() => true))) await mutate();
  }

  if (error) return <ErrorNote error={error} />;
  if (!run || !session) return <Skeleton rows={8} />;

  const nextAction = brief?.sections.next_action?.claims[0]?.text ?? null;
  const needsOverride = !!assessment && (!assessment.score?.qualifies || !!assessment.qualification?.hard_reject);
  const reviewer = can(session, "prospects.review");
  const reviewable = completed && run.review_status === "pending" && reviewer && brief && assessment;

  return (
    <div className="space-y-4">
      <ProfileCard
        tile={<Globe aria-hidden className="h-8 w-8" />}
        title={run.normalised_domain}
        tagline={brief?.summary.company ?? (completed ? undefined : "Research in progress. The brief appears here when it is ready.")}
        tabs={
          completed && (
            <Tabs
              label="Research"
              active={tab}
              onChange={setTab}
              tabs={[
                { key: "brief", label: "Lead brief" },
                { key: "assessment", label: "Opportunities and scores" },
                { key: "intelligence", label: "Intelligence" },
                { key: "pages", label: "Pages crawled" },
              ]}
            />
          )
        }
        badges={
          <>
            <StatusBadge status={run.status} />
            <StatusBadge status={run.review_status} />
          </>
        }
        meta={
          <>
            <SourceLink url={run.input_url} />
            <span>Started {formatDate(run.created_at, true)}</span>
            {run.retry_count > 0 && <span>Attempt {run.retry_count + 1}</span>}
          </>
        }
        actions={
          <>
            {run.account_id && run.review_status !== "approved" && <TextLink href={`/accounts/${run.account_id}`}>Open account</TextLink>}
            {ACTIVE.has(run.status) && (
              <Button busy={action.busy} onClick={() => act("cancel")} icon={<Square className="h-3.5 w-3.5" />}>
                Cancel
              </Button>
            )}
            {(run.status === "failed" || run.status === "cancelled") && (
              <Button busy={action.busy} onClick={() => act("retry")} icon={<RotateCcw className="h-3.5 w-3.5" />}>
                Retry
              </Button>
            )}
          </>
        }
      />
      <ErrorNote error={action.error} />
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
          {tab === "brief" && (brief ? <BriefView brief={brief} /> : <Skeleton rows={8} />)}
          {tab === "assessment" && (assessment ? <AssessmentView assessment={assessment} /> : <Skeleton rows={6} />)}
          {tab === "intelligence" && <IntelligenceView runId={id} />}
          {tab === "pages" && <PagesView run={run} />}
        </>
      )}
      {!completed && run.pages.length > 0 && <PagesView run={run} />}
    </div>
  );
}
