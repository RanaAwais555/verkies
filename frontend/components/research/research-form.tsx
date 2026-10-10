"use client";

import { Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";

import { Button, ErrorNote, inputClass } from "@/components/ui";
import { api } from "@/lib/client";
import { useAction } from "@/lib/hooks";
import type { Run } from "@/lib/types";

/** Start research from a company website; opens the run so its progress is visible. */
export function ResearchForm() {
  const router = useRouter();
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const url = String(new FormData(form).get("url") ?? "").trim();
    const started = await run(() => api<Run>("/research-runs", { method: "POST", body: { url } }));
    if (started) {
      form.reset(); // the app keeps this page alive in the background: leave it ready for the next one
      router.push(`/research/${started.id}`);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input name="url" required placeholder="https://example.co.uk" aria-label="Company website" className={inputClass} />
        <Button type="submit" variant="primary" busy={busy} icon={<Sparkles className="h-4 w-4" />}>
          Research
        </Button>
      </div>
      <ErrorNote error={error} />
    </form>
  );
}
