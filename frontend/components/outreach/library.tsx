"use client";

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Badge, Button, Checkbox, Empty, ErrorNote, Field, IconButton, inputClass, Panel, Skeleton } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { can, useAction, useApi, useSession } from "@/lib/hooks";
import type { OutreachChannel, OutreachSequence, OutreachTemplate } from "@/lib/types";

const CHANNELS: { key: OutreachChannel; label: string }[] = [
  { key: "email", label: "Email" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "call", label: "Call" },
];

function VariableHelp() {
  const { data } = useApi<{ key: string; meaning: string }[]>("/outreach/variables");
  if (!data) return null;
  return (
    <details className="text-xs text-fg-3">
      <summary className="cursor-pointer hover:text-fg">Variables you can use</summary>
      <dl className="mt-1.5 grid gap-x-3 gap-y-1 sm:grid-cols-[9rem_minmax(0,1fr)]">
        {data.map((v) => (
          <div key={v.key} className="contents">
            <dt className="font-mono text-fg-2">{`{${v.key}}`}</dt>
            <dd>{v.meaning}. Left for you to write when VROS has nothing.</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function TemplateForm({ template, onDone }: { template?: OutreachTemplate; onDone: () => void }) {
  const { busy, error, run } = useAction();
  const [channel, setChannel] = useState<OutreachChannel>(template?.channel ?? "email");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      name: String(data.get("name") ?? "").trim(),
      channel,
      subject: channel === "email" ? String(data.get("subject") ?? "").trim() || null : null,
      body: String(data.get("body") ?? ""),
      is_active: data.get("is_active") === "on",
    };
    const ok = await run(() =>
      api(template ? `/outreach/templates/${template.id}` : "/outreach/templates", { method: template ? "PUT" : "POST", body }).then(() => true),
    );
    if (ok) onDone();
  }

  return (
    <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5" data-testid="template-form">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_10rem]">
        <Field label="Name">
          <input name="name" required maxLength={120} defaultValue={template?.name} className={inputClass} />
        </Field>
        <Field label="Channel">
          <select value={channel} onChange={(e) => setChannel(e.target.value as OutreachChannel)} className={inputClass}>
            {CHANNELS.filter((c) => c.key !== "call").map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {channel === "email" && (
        <Field label="Subject" hint="Leave empty for a follow-up: it replies in the same thread.">
          <input name="subject" maxLength={300} defaultValue={template?.subject ?? ""} className={inputClass} />
        </Field>
      )}
      <Field label="Text">
        <textarea name="body" required rows={6} defaultValue={template?.body} className={cx(inputClass, "resize-y leading-relaxed")} />
      </Field>
      <VariableHelp />
      <Checkbox name="is_active" defaultChecked={template?.is_active ?? true} label="In use" />
      <ErrorNote error={error} />
      <div className="flex gap-2">
        <Button type="submit" variant="primary" busy={busy}>
          Save template
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function Templates() {
  const { data: session } = useSession();
  const { data, error, mutate } = useApi<OutreachTemplate[]>("/outreach/templates");
  const [editing, setEditing] = useState<string | null>(null);
  const manager = can(session, "outreach.manage");
  return (
    <Panel
      title="Templates"
      description="Starting points for each step. Variables are filled from the contact, the account and its lead brief."
      actions={
        manager &&
        editing !== "new" && (
          <Button onClick={() => setEditing("new")} icon={<Plus className="h-4 w-4" />}>
            New template
          </Button>
        )
      }
    >
      {editing === "new" && (
        <div className="mb-4">
          <TemplateForm
            onDone={() => {
              setEditing(null);
              mutate();
            }}
          />
        </div>
      )}
      {error && <ErrorNote error={error} />}
      {!data && !error && <Skeleton rows={4} />}
      {data?.length === 0 && <Empty>No templates yet.</Empty>}
      <ul className="divide-y divide-grid" data-testid="templates">
        {data?.map((t) =>
          editing === t.id ? (
            <li key={t.id} className="py-3">
              <TemplateForm
                template={t}
                onDone={() => {
                  setEditing(null);
                  mutate();
                }}
              />
            </li>
          ) : (
            <li key={t.id} className="flex gap-3 py-3 first:pt-0 last:pb-0">
              <div className="min-w-0 flex-1 space-y-1">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-fg">{t.name}</span>
                  <Badge>{t.channel}</Badge>
                  {!t.is_active && <Badge tone="amber">Not in use</Badge>}
                </p>
                {t.subject && <p className="text-xs text-fg-2">Subject: {t.subject}</p>}
                <p className="line-clamp-3 whitespace-pre-line text-xs text-fg-3">{t.body}</p>
              </div>
              {manager && (
                <IconButton label={`Edit ${t.name}`} onClick={() => setEditing(t.id)}>
                  <Pencil className="h-3.5 w-3.5" />
                </IconButton>
              )}
            </li>
          ),
        )}
      </ul>
    </Panel>
  );
}

type StepRow = { channel: OutreachChannel; delay_days: number; template_id: string | null; instructions: string | null };

function SequenceForm({ sequence, templates, onDone }: { sequence?: OutreachSequence; templates: OutreachTemplate[]; onDone: () => void }) {
  const { busy, error, run } = useAction();
  const [steps, setSteps] = useState<StepRow[]>(
    sequence?.steps.map((s) => ({ channel: s.channel, delay_days: s.delay_days, template_id: s.template_id, instructions: s.instructions })) ?? [
      { channel: "email", delay_days: 0, template_id: null, instructions: null },
    ],
  );

  function update(i: number, change: Partial<StepRow>) {
    setSteps(steps.map((s, j) => (j === i ? { ...s, ...change } : s)));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      name: String(data.get("name") ?? "").trim(),
      description: String(data.get("description") ?? "").trim() || null,
      is_active: data.get("is_active") === "on",
      steps: steps.map((s) => ({ ...s, template_id: s.channel === "call" ? null : s.template_id, instructions: s.channel === "call" ? s.instructions : null })),
    };
    const ok = await run(() =>
      api(sequence ? `/outreach/sequences/${sequence.id}` : "/outreach/sequences", { method: sequence ? "PUT" : "POST", body }).then(() => true),
    );
    if (ok) onDone();
  }

  return (
    <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5" data-testid="sequence-form">
      <Field label="Name">
        <input name="name" required maxLength={120} defaultValue={sequence?.name} className={inputClass} />
      </Field>
      <Field label="Description">
        <input name="description" maxLength={2000} defaultValue={sequence?.description ?? ""} className={inputClass} />
      </Field>
      <fieldset className="space-y-2">
        <legend className="mb-1 text-[12.5px] font-medium text-fg-2">Steps</legend>
        {steps.map((s, i) => (
          <div key={i} className="grid items-end gap-2 rounded-lg border border-border bg-surface p-2.5 sm:grid-cols-[7rem_6rem_minmax(0,1fr)_auto]">
            <Field label={`Step ${i + 1}`}>
              <select value={s.channel} onChange={(e) => update(i, { channel: e.target.value as OutreachChannel, template_id: null })} className={inputClass}>
                {CHANNELS.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={i === 0 ? "Days after enrolling" : "Days later"}>
              <input
                type="number"
                min={0}
                max={90}
                value={s.delay_days}
                onChange={(e) => update(i, { delay_days: Number(e.target.value) })}
                className={inputClass}
              />
            </Field>
            {s.channel === "call" ? (
              <Field label="What to do">
                <input value={s.instructions ?? ""} onChange={(e) => update(i, { instructions: e.target.value })} maxLength={2000} className={inputClass} />
              </Field>
            ) : (
              <Field label="Template">
                <select required value={s.template_id ?? ""} onChange={(e) => update(i, { template_id: e.target.value || null })} className={inputClass}>
                  <option value="" disabled>
                    Choose a template
                  </option>
                  {templates
                    .filter((t) => t.channel === s.channel && t.is_active)
                    .map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                </select>
              </Field>
            )}
            <IconButton label={`Remove step ${i + 1}`} onClick={() => setSteps(steps.filter((_, j) => j !== i))} disabled={steps.length === 1}>
              <Trash2 className="h-3.5 w-3.5" />
            </IconButton>
          </div>
        ))}
        <Button
          onClick={() => setSteps([...steps, { channel: "email", delay_days: 2, template_id: null, instructions: null }])}
          icon={<Plus className="h-4 w-4" />}
        >
          Add step
        </Button>
      </fieldset>
      <Checkbox name="is_active" defaultChecked={sequence?.is_active ?? true} label="In use" />
      <ErrorNote error={error} />
      <div className="flex gap-2">
        <Button type="submit" variant="primary" busy={busy}>
          Save sequence
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function Sequences() {
  const { data: session } = useSession();
  const { data, error, mutate } = useApi<OutreachSequence[]>("/outreach/sequences");
  const { data: templates } = useApi<OutreachTemplate[]>("/outreach/templates");
  const [editing, setEditing] = useState<string | null>(null);
  const manager = can(session, "outreach.manage");
  const name = (id: string | null) => templates?.find((t) => t.id === id)?.name ?? "—";
  return (
    <Panel
      title="Sequences"
      description="Steps across email, LinkedIn and calls. Enrolling someone approves the steps; each one still waits for you to do it."
      actions={
        manager &&
        editing !== "new" && (
          <Button onClick={() => setEditing("new")} icon={<Plus className="h-4 w-4" />}>
            New sequence
          </Button>
        )
      }
    >
      {editing === "new" && templates && (
        <div className="mb-4">
          <SequenceForm
            templates={templates}
            onDone={() => {
              setEditing(null);
              mutate();
            }}
          />
        </div>
      )}
      {error && <ErrorNote error={error} />}
      {!data && !error && <Skeleton rows={4} />}
      {data?.length === 0 && <Empty>No sequences yet.</Empty>}
      <ul className="divide-y divide-grid" data-testid="sequences">
        {data?.map((s) =>
          editing === s.id && templates ? (
            <li key={s.id} className="py-3">
              <SequenceForm
                sequence={s}
                templates={templates}
                onDone={() => {
                  setEditing(null);
                  mutate();
                }}
              />
            </li>
          ) : (
            <li key={s.id} className="flex gap-3 py-3 first:pt-0 last:pb-0">
              <div className="min-w-0 flex-1 space-y-1.5">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-fg">{s.name}</span>
                  {!s.is_active && <Badge tone="amber">Not in use</Badge>}
                </p>
                {s.description && <p className="text-xs text-fg-3">{s.description}</p>}
                <ol className="flex flex-wrap gap-1.5 text-xs">
                  {s.steps.map((step, i) => (
                    <li key={step.id} className="rounded-md bg-sunken px-2 py-1 text-fg-2">
                      Day {s.steps.slice(0, i + 1).reduce((sum, x) => sum + x.delay_days, 0)}: {step.channel}
                      {step.channel !== "call" && <span className="text-fg-3"> · {name(step.template_id)}</span>}
                    </li>
                  ))}
                </ol>
              </div>
              {manager && (
                <IconButton label={`Edit ${s.name}`} onClick={() => setEditing(s.id)}>
                  <Pencil className="h-3.5 w-3.5" />
                </IconButton>
              )}
            </li>
          ),
        )}
      </ul>
    </Panel>
  );
}
