"use client";

import { useState, useSyncExternalStore, type FormEvent } from "react";
import useSWR from "swr";
import { useRouter } from "next/navigation";

import { AuthFrame } from "@/components/auth-frame";
import { Button, ErrorNote, Field, inputClass, Loading } from "@/components/ui";
import { api } from "@/lib/client";

type InviteInfo = { email: string; roles: string[]; expires_at: string };

function subscribeToHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
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
  const missing = hash !== null && !token ? new Error("This invite link is incomplete. Ask an admin for a new one.") : null;
  const error = submitError ?? inspectError ?? missing;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    if (form.get("password") !== form.get("confirm")) {
      setError(new Error("The passwords do not match."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api("/auth/invites/accept", {
        method: "POST",
        body: { token, name: form.get("name"), password: form.get("password") },
      });
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
    <AuthFrame title="Join VROS" subtitle="Choose your name and a password to finish setting up your account.">
      {!info && !error && <Loading what="Checking your invite" />}
      {info && (
        <form onSubmit={submit} className="space-y-4">
          <p className="text-sm text-muted">
            Invited as <strong className="text-foreground">{info.email}</strong> ({info.roles.join(", ")}).
          </p>
          <Field label="Your name">
            <input name="name" required maxLength={120} autoComplete="name" className={inputClass} />
          </Field>
          <Field label="Password" hint="At least 12 characters. A passphrase works well.">
            <input name="password" type="password" required minLength={12} autoComplete="new-password" className={inputClass} />
          </Field>
          <Field label="Confirm password">
            <input name="confirm" type="password" required autoComplete="new-password" className={inputClass} />
          </Field>
          <ErrorNote error={error} />
          <Button type="submit" busy={busy} className="w-full">Create account</Button>
        </form>
      )}
      {!info && error ? <ErrorNote error={error} /> : null}
    </AuthFrame>
  );
}
