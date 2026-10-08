"use client";

import { Suspense, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

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
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", { method: "POST", body: { email: form.get("email"), password: form.get("password") } });
      router.replace(next);
    } catch (err) {
      setError(err);
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
    <main className="mx-auto w-full max-w-sm px-4 py-20">
      <h1 className="text-xl font-semibold">Sign in to VROS</h1>
      <p className="mb-6 mt-1 text-sm text-muted">Verkies Revenue Operating System. Access is by invitation.</p>
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
