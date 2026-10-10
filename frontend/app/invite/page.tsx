"use client";

import { Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore, type FormEvent } from "react";
import useSWR from "swr";

import { AuthLayout } from "@/components/auth/auth-layout";
import { PasswordInput } from "@/components/auth/password-input";
import { Badge, Button, ErrorNote, Field, inputClass, Loading } from "@/components/ui";
import { api } from "@/lib/client";
import { formatDate, label } from "@/lib/format";

type InviteInfo = { email: string; roles: string[]; expires_at: string };

function subscribeToHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

/** Length counts for far more than symbols; this only nudges towards a passphrase. */
function strength(password: string): { level: number; text: string } {
  if (!password) return { level: 0, text: "At least 12 characters. Three unrelated words make a strong passphrase." };
  let level = 0;
  if (password.length >= 12) level++;
  if (password.length >= 16) level++;
  if (/[^A-Za-z0-9]/.test(password)) level++;
  if (/\d/.test(password) && /[A-Za-z]/.test(password)) level++;
  const text = password.length < 12 ? `${12 - password.length} more characters needed.` : ["Too easy to guess.", "Reasonable.", "Strong.", "Very strong."][Math.min(3, level - 1)];
  return { level: Math.min(4, level), text };
}

export default function InvitePage() {
  const router = useRouter();
  // The token travels in the URL fragment, which browsers never send to any server.
  const hash = useSyncExternalStore(subscribeToHash, () => window.location.hash, () => null);
  const token = hash === null ? null : new URLSearchParams(hash.slice(1)).get("token");
  const { data: info, error: inspectError } = useSWR<InviteInfo>(
    token ? ["invite", token] : null,
    () => api<InviteInfo>("/auth/invites/inspect", { method: "POST", body: { token } }),
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  const [submitError, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [password, setPassword] = useState("");
  const missing = hash !== null && !token ? new Error("This invitation link is incomplete. Ask an admin to send a new one.") : null;
  const error = submitError ?? inspectError ?? missing;
  const meter = strength(password);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    if (form.get("password") !== form.get("confirm")) {
      setError(new Error("The two passwords do not match."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api("/auth/invites/accept", { method: "POST", body: { token, name: form.get("name"), password: form.get("password") } });
      history.replaceState(null, "", "/invite"); // drop the spent token from the address bar
      element.reset();
      router.replace("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Join the Verkies workspace" subtitle="Choose the name your teammates will see, and a password.">
      {!info && !error && <Loading what="Checking your invitation" />}
      {info && (
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2 rounded-xl border border-border bg-surface-2 p-3.5 text-[13px]">
            <p className="text-fg-2">
              Invited as <strong className="font-semibold text-fg">{info.email}</strong>
            </p>
            <div className="flex flex-wrap items-center gap-1.5">
              {info.roles.map((r) => (
                <Badge key={r} tone="accent">{label(r)}</Badge>
              ))}
              <span className="text-xs text-fg-3">· expires {formatDate(info.expires_at)}</span>
            </div>
            <p className="text-xs text-fg-3">The role decides what you can see and change. The address is fixed by the invitation.</p>
          </div>
          <Field label="Your name">
            <input name="name" required maxLength={120} autoComplete="name" className={inputClass} />
          </Field>
          <Field label="Password" hint={meter.text}>
            <PasswordInput name="password" required minLength={12} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <span aria-hidden className="flex gap-1 pt-0.5">
              {[1, 2, 3, 4].map((n) => (
                <span key={n} className={`h-1 flex-1 rounded-full transition-colors ${meter.level >= n ? "bg-accent" : "bg-track"}`} />
              ))}
            </span>
          </Field>
          <Field label="Confirm password">
            <PasswordInput name="confirm" required autoComplete="new-password" />
          </Field>
          <ErrorNote error={error} />
          <Button type="submit" variant="primary" busy={busy} icon={<Check className="h-4 w-4" />} className="h-11 w-full">
            Create account
          </Button>
        </form>
      )}
      {!info && error ? <ErrorNote error={error} /> : null}
    </AuthLayout>
  );
}
