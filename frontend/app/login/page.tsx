"use client";

import { Suspense, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthFrame } from "@/components/auth-frame";
import { Button, ErrorNote, Field, inputClass } from "@/components/ui";
import { api } from "@/lib/client";

function safeNext(value: string | null): string {
  // Only same-site paths, so a crafted link cannot send people elsewhere after sign-in.
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/";
}

function LoginForm() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", { method: "POST", body: { email: form.get("email"), password: form.get("password") } });
      element.reset(); // the page can be kept in the background; never leave the password in it
      router.replace(next);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Email">
        <input name="email" type="email" autoComplete="username" required className={inputClass} />
      </Field>
      <Field label="Password">
        <input name="password" type="password" autoComplete="current-password" required className={inputClass} />
      </Field>
      <ErrorNote error={error} />
      <Button type="submit" busy={busy} className="w-full">Sign in</Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <AuthFrame title="Sign in to VROS" subtitle="Access is by invitation from your team.">
      <Suspense>
        <LoginForm />
      </Suspense>
    </AuthFrame>
  );
}
