"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button, ErrorNote, inputClass } from "@/components/ui";
import { api } from "@/lib/client";
import type { Run } from "@/lib/types";

export function NewResearchForm() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const url = String(new FormData(event.currentTarget).get("url") ?? "").trim();
    setBusy(true);
    setError(null);
    try {
      const run = await api<Run>("/research-runs", { method: "POST", body: { url } });
      router.push(`/research/${run.id}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="flex gap-2">
        <input
          name="url"
          required
          placeholder="Company website, e.g. https://example.co.uk"
          aria-label="Company website"
          className={inputClass}
        />
        <Button type="submit" busy={busy}>Research</Button>
      </div>
      <ErrorNote error={error} />
    </form>
  );
}
