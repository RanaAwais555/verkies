"use client";

import { Check, Copy, KeyRound, Link2, Pencil, UserPlus, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Badge, Button, Checkbox, Empty, ErrorNote, Field, inputClass, PageHeader, Panel, Skeleton, SourceLink, Success, Tabs } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { formatDate, initials, label, relativeDate } from "@/lib/format";
import { can, useAction, useApi, useSession, useTab } from "@/lib/hooks";
import type { ConfigVersion, Invite, ProviderStatus, Readiness, ReferenceProject, Role, Service, User } from "@/lib/types";

function Profile({ user }: { user: User }) {
  const { busy, error, run } = useAction();
  const [saved, setSaved] = useState(false);

  async function change(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setSaved(false);
    const ok = await run(async () => {
      if (data.get("new_password") !== data.get("confirm")) throw new Error("The new passwords do not match.");
      await api("/auth/password", {
        method: "POST",
        body: { current_password: data.get("current_password"), new_password: data.get("new_password") },
      });
      return true;
    });
    if (ok) {
      form.reset();
      setSaved(true);
    }
  }

  return (
    <div className="grid items-start gap-5 lg:grid-cols-2">
      <Panel title="You">
        <div className="mb-4 flex items-center gap-3">
          <span aria-hidden className="grid h-11 w-11 place-items-center rounded-full bg-accent-soft text-sm font-semibold text-accent-text">
            {initials(user.name)}
          </span>
          <div className="min-w-0">
            <p className="font-medium text-fg">{user.name}</p>
            <p className="truncate text-[13px] text-fg-3">{user.email}</p>
          </div>
        </div>
        <dl className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-y-2.5 text-[13px]">
          <dt className="text-fg-3">Roles</dt>
          <dd className="flex flex-wrap gap-1">
            {user.roles.map((r) => (
              <Badge key={r} tone="accent">
                {label(r)}
              </Badge>
            ))}
          </dd>
          <dt className="text-fg-3">Last sign-in</dt>
          <dd className="text-fg">{formatDate(user.last_login_at, true)}</dd>
        </dl>
      </Panel>
      <Panel title="Change password">
        <form onSubmit={change} className="space-y-3">
          <Field label="Current password">
            <input name="current_password" type="password" required autoComplete="current-password" className={inputClass} />
          </Field>
          <Field label="New password" hint="At least 12 characters. Your other sessions are signed out.">
            <input name="new_password" type="password" required minLength={12} autoComplete="new-password" className={inputClass} />
          </Field>
          <Field label="Confirm new password">
            <input name="confirm" type="password" required autoComplete="new-password" className={inputClass} />
          </Field>
          <ErrorNote error={error} />
          {saved && <Success>Password changed.</Success>}
          <Button type="submit" variant="primary" busy={busy} icon={<KeyRound className="h-4 w-4" />}>
            Change password
          </Button>
        </form>
      </Panel>
    </div>
  );
}

function InviteLink({ link }: { link: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="animate-rise space-y-2 rounded-xl border border-accent/30 bg-accent-soft p-3.5 text-[13px]" data-testid="invite-link">
      <p className="flex items-center gap-2 font-medium text-fg">
        <Link2 aria-hidden className="h-4 w-4 text-accent-text" />
        Send this link to them. It is shown once and expires in 7 days.
      </p>
      <code className="block break-all rounded-lg bg-surface px-2.5 py-2 font-mono text-xs text-fg-2">{link}</code>
      <Button
        onClick={() =>
          navigator.clipboard?.writeText(link).then(
            () => setCopied(true),
            () => setCopied(false),
          )
        }
        icon={copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      >
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}

function Team({ me }: { me: User }) {
  const { data: users, mutate: refreshUsers, error: usersError } = useApi<User[]>("/users");
  const { data: roles } = useApi<Role[]>("/roles");
  const { data: invites, mutate: refreshInvites } = useApi<Invite[]>("/users/invites");
  const { busy, error, run } = useAction();
  const [link, setLink] = useState<string | null>(null);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const created = await run(() => api<Invite>("/users/invites", { method: "POST", body: { email: data.get("email"), roles: data.getAll("roles") } }));
    if (created) {
      setLink(created.invite_url ?? null);
      form.reset();
      refreshInvites();
    }
  }

  async function update(user: User, body: { roles?: string[]; is_active?: boolean }) {
    await run(() => api(`/users/${user.id}`, { method: "PATCH", body }));
    refreshUsers();
  }

  if (usersError) return <ErrorNote error={usersError} />;
  return (
    <div className="flex flex-wrap items-start gap-5">
      <div className="flex min-w-0 flex-[2_1_520px] flex-col gap-5">
        <Panel title={users ? `Members (${users.length})` : "Members"} primary>
          {!users ? (
            <Skeleton rows={4} />
          ) : (
            <ul className="divide-y divide-grid">
              {users.map((u) => (
                <li key={u.id} className={cx("space-y-2 py-3 first:pt-0 last:pb-0", !u.is_active && "opacity-60")}>
                  <div className="flex flex-wrap items-center gap-2.5">
                    <span aria-hidden className="grid h-8 w-8 place-items-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent-text">
                      {initials(u.name)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2 font-medium text-fg">
                        {u.name}
                        {u.id === me.id && <Badge>You</Badge>}
                        {!u.is_active && <Badge tone="red">Deactivated</Badge>}
                      </p>
                      <p className="text-xs text-fg-3">
                        {u.email} · last sign-in {u.last_login_at ? relativeDate(u.last_login_at) : "never"}
                      </p>
                    </div>
                    {u.id !== me.id && (
                      <Button variant={u.is_active ? "ghost" : "secondary"} onClick={() => update(u, { is_active: !u.is_active })}>
                        {u.is_active ? "Deactivate" : "Reactivate"}
                      </Button>
                    )}
                  </div>
                  <div className="ml-[42px] flex flex-wrap gap-x-4 gap-y-1.5">
                    {roles?.map((r) => (
                      <Checkbox
                        key={r.key}
                        label={r.name}
                        className="text-xs"
                        checked={u.roles.includes(r.key)}
                        onChange={(e) => update(u, { roles: e.target.checked ? [...u.roles, r.key] : u.roles.filter((k) => k !== r.key) })}
                      />
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-5">
        <Panel title="Invite a team member" description="Sign-up is by invitation only.">
          <form onSubmit={invite} className="space-y-3">
            <Field label="Email">
              <input name="email" type="email" required className={inputClass} />
            </Field>
            <fieldset>
              <legend className="mb-1.5 text-[12.5px] font-medium text-fg-2">Roles</legend>
              <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                {roles?.map((r) => (
                  <Checkbox key={r.key} name="roles" value={r.key} label={r.name} />
                ))}
              </div>
            </fieldset>
            <ErrorNote error={error} />
            <Button type="submit" variant="primary" busy={busy} icon={<UserPlus className="h-4 w-4" />}>
              Create invite link
            </Button>
            {link && <InviteLink link={link} />}
          </form>
        </Panel>
        <Panel title="Pending invites" collapsible>
          {!invites?.length ? (
            <Empty>No invites waiting.</Empty>
          ) : (
            <ul className="divide-y divide-grid">
              {invites.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center gap-2 py-2.5 text-[13px] first:pt-0 last:pb-0">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-fg">{i.email}</p>
                    <p className="text-xs text-fg-3">
                      {i.roles.map(label).join(", ")} · expires {formatDate(i.expires_at)}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    icon={<X className="h-4 w-4" />}
                    onClick={async () => {
                      await run(() => api(`/users/invites/${i.id}`, { method: "DELETE" }));
                      refreshInvites();
                    }}
                  >
                    Revoke
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

const PROFILE_FIELDS: [keyof ReferenceProject, string][] = [
  ["industry", "Industry"],
  ["business_model", "Business model"],
  ["problem", "Problem solved"],
  ["buyer_type", "Buyer"],
  ["growth_stage", "Growth stage"],
  ["workflow_notes", "Workflows"],
  ["status", "Status"],
];

function ReferenceEditor({ project, services, onSaved, onCancel }: { project: ReferenceProject; services: Service[]; onSaved: () => void; onCancel: () => void }) {
  const { busy, error, run } = useAction();

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body: Record<string, unknown> = Object.fromEntries(PROFILE_FIELDS.map(([k]) => [k, String(data.get(k) ?? "")]));
    body.technologies = String(data.get("technologies") ?? "")
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    body.services = data.getAll("services");
    body.profile_complete = data.get("profile_complete") === "on";
    if (await run(() => api(`/catalogue/reference-projects/${project.id}`, { method: "PATCH", body }).then(() => true))) onSaved();
  }

  return (
    <form onSubmit={save} className="animate-rise mt-2 space-y-3 rounded-xl border border-border bg-surface-2 p-3.5">
      <div className="grid gap-3 sm:grid-cols-2">
        {PROFILE_FIELDS.map(([key, text]) => (
          <Field key={key} label={text} className={key === "problem" || key === "workflow_notes" ? "sm:col-span-2" : undefined}>
            {key === "problem" || key === "workflow_notes" ? (
              <textarea name={key} rows={2} defaultValue={(project[key] as string) ?? ""} className={`${inputClass} h-auto py-2`} />
            ) : (
              <input name={key} defaultValue={(project[key] as string) ?? ""} className={inputClass} />
            )}
          </Field>
        ))}
        <Field label="Technologies" hint="Comma separated." className="sm:col-span-2">
          <input name="technologies" defaultValue={project.technologies.join(", ")} className={inputClass} />
        </Field>
      </div>
      <fieldset>
        <legend className="mb-1.5 text-[12.5px] font-medium text-fg-2">Services delivered</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
          {services.map((s) => (
            <Checkbox key={s.key} name="services" value={s.key} defaultChecked={project.services.includes(s.key)} label={s.name} className="text-xs" />
          ))}
        </div>
      </fieldset>
      <Checkbox name="profile_complete" defaultChecked={project.profile_complete} label="Profile complete (used for similarity; needs industry, problem and a service)" />
      <ErrorNote error={error} />
      <div className="flex gap-2">
        <Button type="submit" variant="primary" busy={busy}>
          Save
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Catalogue({ admin }: { admin: boolean }) {
  const { data: services } = useApi<Service[]>("/catalogue/services");
  const { data: projects, mutate } = useApi<ReferenceProject[]>("/catalogue/reference-projects");
  const [editing, setEditing] = useState<string | null>(null);
  return (
    <div className="grid items-start gap-5 lg:grid-cols-2">
      <Panel title="Services" description="What Verkies sells. Detected opportunities are matched to these.">
        {!services ? (
          <Skeleton rows={4} />
        ) : (
          <ul className="divide-y divide-grid">
            {services.map((s) => (
              <li key={s.id} className="space-y-1 py-2.5 first:pt-0 last:pb-0">
                <p className="flex flex-wrap items-center gap-2 font-medium text-fg">
                  {s.name}
                  {!s.confirmed && <Badge tone="amber">Unconfirmed</Badge>}
                  {!s.is_active && <Badge>Inactive</Badge>}
                </p>
                <p className="text-xs text-fg-3">Solves: {s.solves.map(label).join(", ") || "—"}</p>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Panel title="Reference projects" description="Similarity to past work stays Unknown until a project's profile is complete.">
        {!projects || !services ? (
          <Skeleton rows={4} />
        ) : (
          <ul className="divide-y divide-grid">
            {projects.map((p) => (
              <li key={p.id} className="space-y-1 py-2.5 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-fg">{p.name}</span>
                  {p.profile_complete ? <Badge tone="green">Complete</Badge> : <Badge>Incomplete</Badge>}
                  {admin && editing !== p.id && (
                    <Button variant="ghost" className="ml-auto h-7 px-2 text-xs" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditing(p.id)}>
                      Edit
                    </Button>
                  )}
                </div>
                <p className="text-xs text-fg-3">
                  {p.industry ?? "Industry unknown"} · {p.services.join(", ") || "no services listed"}
                </p>
                {p.source_url && <SourceLink url={p.source_url} />}
                {editing === p.id && (
                  <ReferenceEditor
                    project={p}
                    services={services}
                    onCancel={() => setEditing(null)}
                    onSaved={() => {
                      setEditing(null);
                      mutate();
                    }}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function ConfigEditor({ kind, admin }: { kind: "icp" | "scoring"; admin: boolean }) {
  const { data: active, mutate } = useApi<ConfigVersion>(`/config/${kind}`);
  const { data: versions, mutate: refreshVersions } = useApi<ConfigVersion[]>(`/config/${kind}/versions`);
  const { busy, error, run } = useAction();
  const [text, setText] = useState<string | null>(null);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const note = String(new FormData(event.currentTarget).get("note") ?? "");
    const saved = await run(async () => {
      let config: unknown;
      try {
        config = JSON.parse(text ?? "");
      } catch {
        throw new Error("That is not valid JSON.");
      }
      return api<ConfigVersion>(`/config/${kind}`, { method: "PUT", body: { config, note: note || null } });
    });
    if (saved) {
      setText(null);
      mutate();
      refreshVersions();
    }
  }

  const title = kind === "icp" ? "Ideal customer profile" : "Scoring";
  if (!active) return <Skeleton rows={6} />;
  return (
    <Panel
      title={title}
      collapsible
      actions={<Badge tone="accent">Version {active.version}</Badge>}
      description={`Saving creates a new version; past results keep the version they used. See docs/${kind === "icp" ? "ICP_SPEC" : "SCORING_SPEC"}.md.`}
    >
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_260px]">
        {admin ? (
          <form onSubmit={save} className="space-y-3">
            <textarea
              value={text ?? JSON.stringify(active.config, null, 2)}
              onChange={(e) => setText(e.target.value)}
              rows={18}
              spellCheck={false}
              aria-label={`${kind} configuration`}
              className={`${inputClass} h-auto py-2 font-mono text-xs leading-relaxed`}
            />
            <Field label="What changed and why">
              <input name="note" maxLength={500} className={inputClass} />
            </Field>
            <ErrorNote error={error} />
            <div className="flex gap-2">
              <Button type="submit" variant="primary" busy={busy} disabled={text === null}>
                Save as new version
              </Button>
              {text !== null && (
                <Button variant="ghost" onClick={() => setText(null)}>
                  Discard changes
                </Button>
              )}
            </div>
          </form>
        ) : (
          <pre className="max-h-96 overflow-auto rounded-lg bg-sunken p-3 font-mono text-xs text-fg-2">{JSON.stringify(active.config, null, 2)}</pre>
        )}
        <div>
          <h3 className="mb-2 text-[11px] font-medium uppercase tracking-[0.1em] text-fg-3">History</h3>
          <ol className="space-y-2 border-l border-grid pl-3 text-xs">
            {versions?.map((v) => (
              <li key={v.version} className="relative">
                <span aria-hidden className={cx("absolute -left-[17px] top-1 h-2 w-2 rounded-full", v.is_active ? "bg-accent" : "bg-border-strong")} />
                <p className="text-fg">
                  v{v.version}
                  {v.is_active && <span className="text-accent-text"> · active</span>}
                </p>
                <p className="text-fg-3">{formatDate(v.created_at, true)}</p>
                {v.note && <p className="text-fg-2">{v.note}</p>}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </Panel>
  );
}

const PROVIDER_TONE = { ok: "green", degraded: "amber", off: "neutral" } as const;

function Providers() {
  const { data, error } = useApi<ProviderStatus[]>("/system/providers");
  if (error) return <ErrorNote error={error} />;
  return (
    <Panel title="Data sources" description="What VROS can reach on this server. Nothing switched off is ever shown as data.">
      {!data ? (
        <Skeleton rows={4} />
      ) : (
        <ul className="divide-y divide-grid" data-testid="providers">
          {data.map((p) => (
            <li key={p.name} className="flex flex-wrap items-center gap-2 py-2.5 text-[13px] first:pt-0 last:pb-0">
              <Badge tone={PROVIDER_TONE[p.status]}>{p.status === "ok" ? "On" : p.status === "off" ? "Off" : "Needs setup"}</Badge>
              <span className="font-medium text-fg">{p.name}</span>
              <span className="text-fg-3">{p.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function SystemStatus() {
  const { data, error } = useApi<Readiness>("/health/ready", { shouldRetryOnError: false });
  if (error && !data) return <ErrorNote error={error} />;
  return (
    <Panel title="System status">
      {!data ? (
        <Skeleton rows={3} />
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {Object.entries(data.checks).map(([name, check]) => (
            <li key={name} className="flex items-center gap-2.5 rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-[13px]">
              <span aria-hidden className={cx("h-2 w-2 rounded-full", check.status === "ok" ? "bg-ok" : "bg-bad")} />
              <span className="font-medium capitalize text-fg">{name}</span>
              <span className="ml-auto text-fg-3">{check.status === "ok" ? "Working" : `Down (${check.error})`}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export default function SettingsPage() {
  const { data: session } = useSession();
  const [tab, setTab] = useTab("profile");
  if (!session) return <Skeleton rows={6} />;
  const configAdmin = can(session, "config.manage");
  const tabs = [
    { key: "profile", label: "Profile" },
    ...(can(session, "users.manage") ? [{ key: "team", label: "Team" }] : []),
    { key: "catalogue", label: "Services and references" },
    ...(can(session, "config.manage", "research.run", "accounts.read", "accounts.read_own") ? [{ key: "config", label: "ICP and scoring" }] : []),
    { key: "system", label: "System" },
  ];
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Management" title="Settings" description="Your profile, the team, what Verkies sells, and how prospects are qualified and scored." />
      <Tabs label="Settings sections" tabs={tabs} active={tab} onChange={setTab} />
      {tab === "profile" && <Profile user={session.user} />}
      {tab === "team" && <Team me={session.user} />}
      {tab === "catalogue" && <Catalogue admin={configAdmin} />}
      {tab === "config" && (
        <div className="space-y-5">
          <ConfigEditor kind="icp" admin={configAdmin} />
          <ConfigEditor kind="scoring" admin={configAdmin} />
        </div>
      )}
      {tab === "system" && (
        <div className="space-y-5">
          <SystemStatus />
          <Providers />
        </div>
      )}
    </div>
  );
}
