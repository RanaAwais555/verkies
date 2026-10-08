"use client";

import { useState, type FormEvent } from "react";

import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorNote,
  Field,
  formatDate,
  inputClass,
  label,
  Loading,
  PageHeader,
  SourceLink,
  Success,
  Tabs,
} from "@/components/ui";
import { api } from "@/lib/client";
import { can, useApi, useSession, useTab } from "@/lib/hooks";
import type { ConfigVersion, Invite, ReferenceProject, Role, Service, User } from "@/lib/types";

function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (err) {
      setError(err);
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run };
}

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
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="You">
        <dl className="grid grid-cols-[6rem_1fr] gap-y-1 text-sm">
          <dt className="text-muted">Name</dt><dd>{user.name}</dd>
          <dt className="text-muted">Email</dt><dd>{user.email}</dd>
          <dt className="text-muted">Roles</dt><dd>{user.roles.map(label).join(", ")}</dd>
        </dl>
      </Card>
      <Card title="Change password">
        <form onSubmit={change} className="space-y-3">
          <Field label="Current password"><input name="current_password" type="password" required autoComplete="current-password" className={inputClass} /></Field>
          <Field label="New password" hint="At least 12 characters. Other sessions are signed out."><input name="new_password" type="password" required minLength={12} autoComplete="new-password" className={inputClass} /></Field>
          <Field label="Confirm new password"><input name="confirm" type="password" required autoComplete="new-password" className={inputClass} /></Field>
          <ErrorNote error={error} />
          {saved && <Success>Password changed.</Success>}
          <Button type="submit" busy={busy}>Change password</Button>
        </form>
      </Card>
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
    const created = await run(() =>
      api<Invite>("/users/invites", { method: "POST", body: { email: data.get("email"), roles: data.getAll("roles") } }),
    );
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
    <div className="space-y-4">
      <Card title="Invite a team member">
        <form onSubmit={invite} className="space-y-3">
          <Field label="Email"><input name="email" type="email" required className={`${inputClass} max-w-sm`} /></Field>
          <fieldset className="text-sm">
            <legend className="mb-1 font-medium">Roles</legend>
            <div className="flex flex-wrap gap-3">
              {roles?.map((r) => (
                <label key={r.key} className="flex items-center gap-1"><input type="checkbox" name="roles" value={r.key} /> {r.name}</label>
              ))}
            </div>
          </fieldset>
          <ErrorNote error={error} />
          <Button type="submit" busy={busy}>Create invite link</Button>
          {link && (
            <div className="space-y-1 rounded-md border border-border p-3 text-sm" data-testid="invite-link">
              <p className="font-medium">Send this link to them. It is shown once and expires in 7 days.</p>
              <code className="block break-all text-xs">{link}</code>
              <Button type="button" variant="secondary" onClick={() => navigator.clipboard?.writeText(link)}>Copy</Button>
            </div>
          )}
        </form>
      </Card>
      <Card title="Pending invites">
        {!invites?.length ? <Empty>None.</Empty> : (
          <ul className="space-y-1 text-sm">
            {invites.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-2">
                <span>{i.email}</span>
                <span className="text-xs text-muted">{i.roles.join(", ")} · expires {formatDate(i.expires_at)}</span>
                <Button variant="ghost" onClick={async () => { await run(() => api(`/users/invites/${i.id}`, { method: "DELETE" })); refreshInvites(); }}>Revoke</Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Team">
        {!users ? <Loading /> : (
          <ul className="divide-y divide-border text-sm">
            {users.map((u) => (
              <li key={u.id} className="space-y-1 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{u.name}</span>
                  <span className="text-muted">{u.email}</span>
                  {!u.is_active && <Badge tone="red">Deactivated</Badge>}
                  <span className="text-xs text-muted">last sign-in {formatDate(u.last_login_at, true)}</span>
                  {u.id !== me.id && (
                    <Button variant="ghost" onClick={() => update(u, { is_active: !u.is_active })}>
                      {u.is_active ? "Deactivate" : "Reactivate"}
                    </Button>
                  )}
                </div>
                <div className="flex flex-wrap gap-3">
                  {roles?.map((r) => (
                    <label key={r.key} className="flex items-center gap-1 text-xs">
                      <input
                        type="checkbox"
                        checked={u.roles.includes(r.key)}
                        onChange={(e) => update(u, { roles: e.target.checked ? [...u.roles, r.key] : u.roles.filter((k) => k !== r.key) })}
                      />
                      {r.name}
                    </label>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
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

function ReferenceEditor({ project, services, onSaved }: { project: ReferenceProject; services: Service[]; onSaved: () => void }) {
  const { busy, error, run } = useAction();

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body: Record<string, unknown> = Object.fromEntries(PROFILE_FIELDS.map(([k]) => [k, String(data.get(k) ?? "")]));
    body.technologies = String(data.get("technologies") ?? "").split(",").map((t) => t.trim()).filter(Boolean);
    body.services = data.getAll("services");
    body.profile_complete = data.get("profile_complete") === "on";
    if (await run(() => api(`/catalogue/reference-projects/${project.id}`, { method: "PATCH", body }))) onSaved();
  }

  return (
    <form onSubmit={save} className="space-y-2 rounded-md border border-border p-3">
      {PROFILE_FIELDS.map(([key, text]) => (
        <Field key={key} label={text}>
          {key === "problem" || key === "workflow_notes"
            ? <textarea name={key} rows={2} defaultValue={(project[key] as string) ?? ""} className={inputClass} />
            : <input name={key} defaultValue={(project[key] as string) ?? ""} className={inputClass} />}
        </Field>
      ))}
      <Field label="Technologies" hint="Comma separated.">
        <input name="technologies" defaultValue={project.technologies.join(", ")} className={inputClass} />
      </Field>
      <fieldset className="text-sm">
        <legend className="mb-1 font-medium">Services delivered</legend>
        <div className="flex flex-wrap gap-3">
          {services.map((s) => (
            <label key={s.key} className="flex items-center gap-1 text-xs">
              <input type="checkbox" name="services" value={s.key} defaultChecked={project.services.includes(s.key)} /> {s.name}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="profile_complete" defaultChecked={project.profile_complete} />
        Profile complete (used for similarity; needs industry, problem and a service)
      </label>
      <ErrorNote error={error} />
      <Button type="submit" busy={busy}>Save</Button>
    </form>
  );
}

function Catalogue({ admin }: { admin: boolean }) {
  const { data: services } = useApi<Service[]>("/catalogue/services");
  const { data: projects, mutate } = useApi<ReferenceProject[]>("/catalogue/reference-projects");
  const [editing, setEditing] = useState<string | null>(null);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Services">
        {!services ? <Loading /> : (
          <ul className="space-y-2 text-sm">
            {services.map((s) => (
              <li key={s.id}>
                <span className="font-medium">{s.name}</span> {!s.confirmed && <Badge tone="amber">Unconfirmed</Badge>}
                <p className="text-xs text-muted">Solves: {s.solves.map(label).join(", ") || "—"}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Reference projects">
        <p className="mb-3 text-xs text-muted">Similarity to past work stays Unknown until a project&apos;s profile is complete.</p>
        {!projects || !services ? <Loading /> : (
          <ul className="space-y-3 text-sm">
            {projects.map((p) => (
              <li key={p.id} className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{p.name}</span>
                  {p.profile_complete ? <Badge tone="green">Complete</Badge> : <Badge>Incomplete</Badge>}
                  {admin && <Button variant="ghost" onClick={() => setEditing(editing === p.id ? null : p.id)}>{editing === p.id ? "Close" : "Edit"}</Button>}
                </div>
                <p className="text-xs text-muted">{p.industry ?? "Industry unknown"} · {p.services.join(", ") || "no services listed"}</p>
                {p.source_url && <SourceLink url={p.source_url} />}
                {editing === p.id && <ReferenceEditor project={p} services={services} onSaved={() => { setEditing(null); mutate(); }} />}
              </li>
            ))}
          </ul>
        )}
      </Card>
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

  if (!active) return <Loading />;
  return (
    <Card title={`${kind === "icp" ? "ICP" : "Scoring"} configuration · version ${active.version}`}>
      <p className="mb-2 text-xs text-muted">
        Saving creates a new version; past results keep the version they used. See docs/{kind === "icp" ? "ICP_SPEC" : "SCORING_SPEC"}.md.
      </p>
      {admin ? (
        <form onSubmit={save} className="space-y-2">
          <textarea
            value={text ?? JSON.stringify(active.config, null, 2)}
            onChange={(e) => setText(e.target.value)}
            rows={18}
            spellCheck={false}
            aria-label={`${kind} configuration`}
            className={`${inputClass} font-mono text-xs`}
          />
          <Field label="What changed and why"><input name="note" maxLength={500} className={inputClass} /></Field>
          <ErrorNote error={error} />
          <Button type="submit" busy={busy} disabled={text === null}>Save as new version</Button>
        </form>
      ) : (
        <pre className="max-h-96 overflow-auto rounded bg-surface p-2 text-xs">{JSON.stringify(active.config, null, 2)}</pre>
      )}
      <ul className="mt-3 space-y-1 text-xs text-muted">
        {versions?.map((v) => (
          <li key={v.version}>v{v.version} · {formatDate(v.created_at, true)}{v.is_active ? " · active" : ""}{v.note ? ` · ${v.note}` : ""}</li>
        ))}
      </ul>
    </Card>
  );
}

function Providers() {
  const { data, error } = useApi<{ name: string; status: "ok" | "degraded" | "off"; detail: string }[]>("/system/providers");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const tone = { ok: "green", degraded: "amber", off: "neutral" } as const;
  return (
    <Card title="Data sources">
      <ul className="space-y-2 text-sm" data-testid="providers">
        {data.map((p) => (
          <li key={p.name} className="flex flex-wrap items-center gap-2">
            <Badge tone={tone[p.status]}>{p.status === "ok" ? "On" : p.status === "off" ? "Off" : "Needs setup"}</Badge>
            <span className="font-medium">{p.name}</span>
            <span className="text-muted">{p.detail}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function SystemStatus() {
  const { data, error } = useApi<{ status: string; checks: Record<string, { status: string; error: string | null }> }>("/health/ready", { shouldRetryOnError: false });
  if (error && !data) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  return (
    <Card title="System status">
      <ul className="space-y-1 text-sm">
        {Object.entries(data.checks).map(([name, check]) => (
          <li key={name} className="flex items-center gap-2">
            <span aria-hidden className={`inline-block h-2 w-2 rounded-full ${check.status === "ok" ? "bg-green-500" : "bg-red-500"}`} />
            <span className="capitalize">{name}</span>
            <span className="text-muted">{check.status === "ok" ? "ok" : `down (${check.error})`}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function SettingsPage() {
  const { data: session } = useSession();
  const [tab, setTab] = useTab("profile");
  if (!session) return <Loading />;
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
      <PageHeader title="Settings" description="Your profile, the team, what Verkies sells, and how prospects are qualified and scored." />
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "profile" && <Profile user={session.user} />}
      {tab === "team" && <Team me={session.user} />}
      {tab === "catalogue" && <Catalogue admin={configAdmin} />}
      {tab === "config" && (
        <div className="space-y-4">
          <ConfigEditor kind="icp" admin={configAdmin} />
          <ConfigEditor kind="scoring" admin={configAdmin} />
        </div>
      )}
      {tab === "system" && (
        <div className="space-y-4">
          <SystemStatus />
          <Providers />
        </div>
      )}
    </div>
  );
}
