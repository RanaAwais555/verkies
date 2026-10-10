"use client";

import { ArrowRight, KeyRound } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { PasswordInput } from "@/components/auth/password-input";
import { Button, ErrorNote, Field, inputClass } from "@/components/ui";
import { api } from "@/lib/client";

function safeNext(value: string | null): string {
  // Only same-site paths, so a crafted link cannot send someone elsewhere after signing in.
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
      element.reset(); // the page can be kept in the background: never leave the password in it
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
        <input name="email" type="email" autoComplete="username" required placeholder="you@verkies.co" className={inputClass} />
      </Field>
      <Field label="Password">
        <PasswordInput name="password" autoComplete="current-password" required />
      </Field>
      <ErrorNote error={error} />
      <Button type="submit" variant="primary" busy={busy} icon={<ArrowRight className="h-4 w-4" />} className="h-11 w-full">
        Sign in
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <AuthLayout
      title="Sign in"
      subtitle="Use the work address your invitation was sent to."
      footer={
        <p className="flex gap-2.5 text-[12.5px] leading-relaxed text-fg-2">
          <KeyRound aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-accent-text" />
          <span>
            <strong className="font-semibold text-fg">VROS is invite only.</strong> There is no public sign-up: an admin sends an invitation, and the role it
            carries decides what you can reach. Forgotten your password? Ask an admin to send a new invitation.
          </span>
        </p>
      }
    >
      <Suspense>
        <LoginForm />
      </Suspense>
    </AuthLayout>
  );
}
