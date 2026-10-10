import { EvidenceList } from "@/components/research/evidence";
import { Badge, Empty, Note, Panel, Score, ScoreBar } from "@/components/ui";
import { label, percent } from "@/lib/format";
import type { Assessment } from "@/lib/types";

/** What the engines found: evidenced opportunities, the ICP qualification and the scores. */
export function AssessmentView({ assessment }: { assessment: Assessment }) {
  const { qualification: q, score } = assessment;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title="Detected opportunities" className="xl:col-span-2">
        {assessment.opportunities.length === 0 ? (
          <Empty>No evidenced opportunity.</Empty>
        ) : (
          <ul className="divide-y divide-grid">
            {assessment.opportunities.map((o) => (
              <li key={o.id} className="space-y-1.5 py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-fg">{o.title}</span>
                  <Badge>{label(o.category)}</Badge>
                  <span className="text-xs text-fg-3">confidence {percent(o.confidence)}</span>
                </div>
                <p className="text-[13px] text-fg-2">{o.problem}</p>
                <EvidenceList evidence={o.evidence} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
      {q && (
        <Panel title="Qualification (ICP)">
          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            <span className="text-fg-2">ICP fit</span>
            <Score value={q.icp_fit} className="font-semibold text-fg" />
            {q.hard_reject && <Badge tone="red">Rejected: {label(q.rejection_reason ?? "")}</Badge>}
          </div>
          <p className="mt-3 whitespace-pre-line text-[13px] leading-relaxed text-fg-2">{q.explanation}</p>
        </Panel>
      )}
      {score && (
        <Panel title="Scores">
          <div className="space-y-2">
            {Object.entries(score.scores).map(([k, v]) => (
              <ScoreBar key={k} name={k} value={v} />
            ))}
          </div>
          {score.not_qualified_because.length > 0 && <Note className="mt-3">Not qualified because: {score.not_qualified_because.join("; ")}</Note>}
        </Panel>
      )}
    </div>
  );
}
