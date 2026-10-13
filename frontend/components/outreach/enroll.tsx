"use client";

import { CircleStop, ListChecks } from "lucide-react";
import { useState } from "react";

import { Badge, Button, ErrorNote, Field, inputClass, Skeleton } from "@/components/ui";
import { api } from "@/lib/client";
import { formatDate } from "@/lib/format";
import { useAction, useApi, useCanChange } from "@/lib/hooks";
import type { Contact, Enrollment, OutreachSequence, SequencePreview } from "@/lib/types";

/**
 * Choose a sequence and review every step as it would read for this person. "Approve sequence"
 * is the approval §12B asks for; each step still waits in your queue for you to do it.
 */
export function EnrollPanel({ contact, onDone, onCancel }: { contact: Pick<Contact, "id" | "name">; onDone: () => void; onCancel: () => void }) {
  const { data: sequences } = useApi<OutreachSequence[]>("/outreach/sequences");
  const active = sequences?.filter((s) => s.is_active) ?? [];
  const [chosen, setChosen] = useState<string>("");
  const sequenceId = chosen || active[0]?.id || "";
  const { data: preview, error } = useApi<SequencePreview>(sequenceId ? `/outreach/sequences/${sequenceId}/preview?contact_id=${contact.id}` : null);
  const { busy, error: enrollError, run } = useAction();

  return (
    <div className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5" data-testid="enroll-panel">
      {!sequences && <Skeleton rows={2} />}
      {sequences && active.length === 0 && <p className="text-[13px] text-fg-3">No sequence is in use. Someone who manages outreach can add one.</p>}
      {active.length > 0 && (
        <Field label="Sequence">
          <select value={sequenceId} onChange={(e) => setChosen(e.target.value)} className={inputClass}>
            {active.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.steps.length} steps)
              </option>
            ))}
          </select>
        </Field>
      )}
      {error && <ErrorNote error={error} />}
      {preview && (
        <ol className="space-y-2" aria-label={`The steps for ${contact.name}`}>
          {preview.steps.map((s) => (
            <li key={s.position} className="rounded-lg border border-border bg-surface p-2.5 text-[13px]">
              <p className="flex flex-wrap items-center gap-2 text-xs text-fg-3">
                <Badge>{s.channel}</Badge>
                Step {s.position + 1} · due about {formatDate(s.due_at)}
                {s.draft.missing.length > 0 && <Badge tone="amber">To write: {s.draft.missing.join(", ")}</Badge>}
              </p>
              {s.draft.subject && <p className="mt-1 font-medium text-fg">{s.draft.subject}</p>}
              <p className="mt-0.5 line-clamp-4 whitespace-pre-line text-fg-2">{s.draft.body}</p>
            </li>
          ))}
        </ol>
      )}
      <ErrorNote error={enrollError} />
      <div className="flex flex-wrap gap-2">
        <Button
          variant="primary"
          busy={busy}
          disabled={!preview}
          icon={<ListChecks className="h-4 w-4" />}
          onClick={async () => {
            if (await run(() => api("/outreach/enrollments", { method: "POST", body: { sequence_id: sequenceId, contact_id: contact.id } }).then(() => true)))
              onDone();
          }}
        >
          Approve sequence
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

/** Where a person is in a sequence, with a way to stop it. */
export function EnrollmentLine({ enrollment, onChange }: { enrollment: Enrollment; onChange: () => void }) {
  const { busy, error, run } = useAction();
  const writable = useCanChange();
  if (enrollment.status !== "active") {
    return (
      <p className="text-xs text-fg-3">
        {enrollment.sequence_name}: {enrollment.status === "completed" ? "finished" : `stopped (${enrollment.stop_reason})`}
      </p>
    );
  }
  return (
    <span className="flex flex-wrap items-center gap-2 text-xs text-fg-3" data-testid="enrollment">
      <Badge tone="accent">In {enrollment.sequence_name}</Badge>
      step {enrollment.next_position + 1} of {enrollment.total_steps}
      {enrollment.next_due_at && ` · due ${formatDate(enrollment.next_due_at)}`}
      {writable && (
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          if (await run(() => api(`/outreach/enrollments/${enrollment.id}/stop`, { method: "POST", body: { reason: "Stopped by hand" } }).then(() => true)))
            onChange();
        }}
        className="inline-flex items-center gap-1 text-fg-3 hover:text-bad"
      >
        <CircleStop aria-hidden className="h-3.5 w-3.5" />
        Stop
      </button>
      )}
      <ErrorNote error={error} />
    </span>
  );
}
