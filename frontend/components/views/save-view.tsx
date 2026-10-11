"use client";

import { BookmarkPlus, Check } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button, Checkbox, ErrorNote, inputClass } from "@/components/ui";
import { api } from "@/lib/client";
import { can, useAction, useSession } from "@/lib/hooks";

/**
 * Save the page as it is now (its address and filters) as a named view. The view stores only the
 * link, so opening it later shows that day's data. Anyone who manages configuration can share it.
 */
export function SaveViewButton({ suggestedName = "" }: { suggestedName?: string }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const { data: session } = useSession();
  const { busy, error, run } = useAction();
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const name = String(data.get("name") ?? "").trim();
    const ok = await run(() =>
      api("/saved-views", {
        method: "POST",
        body: { name, path: pathname, query: params.toString(), shared: data.get("shared") === "on" },
      }).then(() => true),
    );
    if (ok) {
      setOpen(false);
      setSaved(name);
    }
  }

  if (saved) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[13px] text-ok" role="status">
        <Check aria-hidden className="h-4 w-4" />
        Saved as &ldquo;{saved}&rdquo;.{" "}
        <Link href="/views" className="text-accent-text hover:underline">
          Saved views
        </Link>
      </span>
    );
  }
  if (!open) {
    return (
      <Button icon={<BookmarkPlus className="h-4 w-4" />} onClick={() => setOpen(true)}>
        Save view
      </Button>
    );
  }
  return (
    <form onSubmit={submit} className="animate-rise flex flex-wrap items-center gap-2" data-testid="save-view">
      <input
        name="name"
        required
        maxLength={80}
        defaultValue={suggestedName}
        aria-label="View name"
        placeholder="Name this view"
        autoFocus
        className={`${inputClass} w-52`}
      />
      {can(session, "config.manage") && <Checkbox name="shared" label="Share with the team" />}
      <Button type="submit" variant="primary" busy={busy}>
        Save
      </Button>
      <Button variant="ghost" onClick={() => setOpen(false)}>
        Cancel
      </Button>
      <div className="basis-full empty:hidden">
        <ErrorNote error={error} />
      </div>
    </form>
  );
}
