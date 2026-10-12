"use client";

import { Pencil, Plus, Trash2, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Badge, Button, Checkbox, Empty, ErrorNote, Field, inputClass, Panel, Skeleton, Table, type Tone } from "@/components/ui";
import { api } from "@/lib/client";
import { can, useAction, useApi, useSession } from "@/lib/hooks";
import type { AlertRule, RuleChoices } from "@/lib/types";

const ACTION_TONE: Record<string, Tone> = { opportunity_detected: "green", requires_review: "red", task: "blue" };

type Draft = Pick<AlertRule, "name" | "active" | "kinds" | "signals" | "topics" | "action" | "task_title">;

const EMPTY: Draft = { name: "", active: true, kinds: [], signals: [], topics: [], action: "requires_review", task_title: null };

function names(keys: string[], choices: { key: string; label: string }[]) {
  return keys.map((k) => choices.find((c) => c.key === k)?.label ?? k);
}

/** What a rule matches, in words: "Website change about Pricing or Services". */
function when(rule: Draft, choices: RuleChoices) {
  const parts: string[] = [];
  if (rule.kinds.length) parts.push(names(rule.kinds, choices.kinds).join(" or "));
  if (rule.signals.length) parts.push(`signal: ${names(rule.signals, choices.signals).join(", ")}`);
  if (rule.topics.length) parts.push(`about ${names(rule.topics, choices.topics).join(" or ")}`);
  return parts.join(" · ");
}

function Picks({
  legend,
  options,
  value,
  onChange,
}: {
  legend: string;
  options: { key: string; label: string }[];
  value: string[];
  onChange: (v: string[]) => void;
}) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-xs font-medium text-fg-2">{legend}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {options.map((o) => (
          <Checkbox
            key={o.key}
            label={o.label}
            checked={value.includes(o.key)}
            onChange={(e) => onChange(e.target.checked ? [...value, o.key] : value.filter((k) => k !== o.key))}
          />
        ))}
      </div>
    </fieldset>
  );
}

function RuleForm({ initial, choices, onDone }: { initial: AlertRule | null; choices: RuleChoices; onDone: () => void }) {
  const [draft, setDraft] = useState<Draft>(initial ?? EMPTY);
  const { busy, error, run } = useAction();
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));
  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = { ...draft, task_title: draft.action === "task" ? draft.task_title : null };
    const ok = await run(() =>
      initial ? api(`/monitoring/rules/${initial.id}`, { method: "PATCH", body }) : api("/monitoring/rules", { method: "POST", body }),
    );
    if (ok) onDone();
  }
  return (
    <form onSubmit={submit} className="space-y-4 rounded-xl border border-border bg-surface-2 p-4" data-testid="rule-form">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Rule name">
          <input className={inputClass} value={draft.name} onChange={(e) => set({ name: e.target.value })} required maxLength={120} />
        </Field>
        <Field label="Then">
          <select className={inputClass} value={draft.action} onChange={(e) => set({ action: e.target.value as Draft["action"] })}>
            {choices.actions.map((a) => (
              <option key={a.key} value={a.key}>
                {a.key === "task" ? "Create a follow-up task for the owner" : `Raise ${a.label}`}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <p className="text-xs text-fg-3">When monitoring finds an alert that matches every list you tick. An empty list matches anything; tick at least one.</p>
      <Picks legend="Kind of alert" options={choices.kinds} value={draft.kinds} onChange={(kinds) => set({ kinds })} />
      <Picks legend="Signal" options={choices.signals} value={draft.signals} onChange={(signals) => set({ signals })} />
      <Picks legend="Website change about" options={choices.topics} value={draft.topics} onChange={(topics) => set({ topics })} />
      {draft.action === "task" && (
        <Field label="Task title" hint="Optional. {account} becomes the account's name. One open task per rule and account.">
          <input
            className={inputClass}
            value={draft.task_title ?? ""}
            onChange={(e) => set({ task_title: e.target.value })}
            placeholder={`Follow up: ${draft.name || "rule name"}`}
            maxLength={200}
          />
        </Field>
      )}
      <Checkbox label="Active" checked={draft.active} onChange={(e) => set({ active: e.target.checked })} />
      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={busy}>
          {initial ? "Save rule" : "Add rule"}
        </Button>
        <Button onClick={onDone} icon={<X className="h-4 w-4" />}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Alert rules (slice 6.3): what monitoring alerts raise. Admins change them; everyone sees them. */
export function AlertRules() {
  const { data: session } = useSession();
  const { data, error } = useApi<AlertRule[]>("/monitoring/rules");
  const { data: choices } = useApi<RuleChoices>("/monitoring/rule-choices");
  const [editing, setEditing] = useState<AlertRule | "new" | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const { error: actionError, run } = useAction();
  const admin = can(session, "config.manage");
  return (
    <Panel
      title="Alert rules"
      description="When monitoring finds something that matches a rule, the alert is flagged Opportunity Detected or Requires review, or the account's manager or owner gets a follow-up task. Nobody is contacted."
      actions={
        admin &&
        editing === null && (
          <Button icon={<Plus className="h-4 w-4" />} onClick={() => setEditing("new")}>
            New rule
          </Button>
        )
      }
      testId="alert-rules"
    >
      <div className="space-y-4">
        {editing !== null && choices && <RuleForm initial={editing === "new" ? null : editing} choices={choices} onDone={() => setEditing(null)} />}
        <ErrorNote error={error ?? actionError} />
        {!data || !choices ? (
          !error && <Skeleton rows={3} />
        ) : data.length === 0 ? (
          <Empty>No alert rules. Alerts are listed but nothing is flagged.</Empty>
        ) : (
          <Table testId="rules">
            <thead>
              <tr>
                <th>Rule</th>
                <th>When</th>
                <th>Then</th>
                {admin && <th />}
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} data-testid="rule-row" className={r.active ? undefined : "opacity-60"}>
                  <td className="min-w-[10rem] font-medium text-fg">
                    {r.name}
                    {!r.active && <span className="block text-xs font-normal text-fg-3">Switched off</span>}
                  </td>
                  <td className="min-w-[14rem] text-fg-2">{when(r, choices)}</td>
                  <td className="min-w-[10rem]">
                    <Badge tone={ACTION_TONE[r.action] ?? "neutral"}>{choices.actions.find((a) => a.key === r.action)?.label ?? r.action}</Badge>
                    {r.action === "task" && r.task_title && <span className="mt-1 block text-xs text-fg-3">{r.task_title}</span>}
                  </td>
                  {admin && (
                    <td className="whitespace-nowrap text-right">
                      <Button
                        variant="ghost"
                        className="h-7 px-2"
                        aria-label={`Edit ${r.name}`}
                        icon={<Pencil className="h-3.5 w-3.5" />}
                        onClick={() => setEditing(r)}
                      >
                        Edit
                      </Button>
                      {confirming === r.id ? (
                        <Button
                          variant="ghost"
                          className="h-7 px-2 text-bad"
                          aria-label={`Confirm deleting ${r.name}`}
                          icon={<Trash2 className="h-3.5 w-3.5" />}
                          onClick={() => run(() => api(`/monitoring/rules/${r.id}`, { method: "DELETE" }))}
                        >
                          Confirm delete
                        </Button>
                      ) : (
                        <Button
                          variant="ghost"
                          className="h-7 px-2"
                          aria-label={`Delete ${r.name}`}
                          icon={<Trash2 className="h-3.5 w-3.5" />}
                          onClick={() => setConfirming(r.id)}
                        >
                          Delete
                        </Button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </div>
    </Panel>
  );
}
