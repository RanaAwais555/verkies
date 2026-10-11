"use client";

import { Save, UserPlus } from "lucide-react";
import type { FormEvent } from "react";

import { Button, ErrorNote, Field, inputClass } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { label } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import { DECISION_MAKER_ROLES, type Contact } from "@/lib/types";

/**
 * Add a person to an account, or edit one. A person added here is sourced "manual" and stays
 * unverified until someone marks it verified. Addresses on the suppression list are refused.
 */
export function ContactForm({
  accountId,
  contact,
  onSaved,
  onCancel,
}: {
  accountId: string;
  /** Edit this contact; without it the form adds a new one. */
  contact?: Contact;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const text = (name: string) => String(data.get(name) ?? "").trim() || null;
    const body: Record<string, unknown> = {
      name: text("name"),
      title: text("title"),
      department: text("department"),
      email: text("email"),
      phone: text("phone"),
      linkedin_url: text("linkedin_url"),
      decision_maker_role: text("role"),
      notes: text("notes"),
    };
    if (contact) body.verification_status = data.get("verified") ? "verified" : "unverified";
    const saved = await run(() =>
      api(contact ? `/contacts/${contact.id}` : `/accounts/${accountId}/contacts`, { method: contact ? "PATCH" : "POST", body }).then(() => true),
    );
    if (saved) onSaved();
  }

  return (
    <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5" data-testid="contact-form">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <input name="name" required maxLength={200} defaultValue={contact?.name} className={inputClass} />
        </Field>
        <Field label="Job title">
          <input name="title" maxLength={200} defaultValue={contact?.title ?? ""} className={inputClass} />
        </Field>
        <Field label="Email">
          <input name="email" type="email" maxLength={320} defaultValue={contact?.email ?? ""} className={inputClass} />
        </Field>
        <Field label="Phone">
          <input name="phone" type="tel" maxLength={40} defaultValue={contact?.phone ?? ""} className={inputClass} />
        </Field>
        <Field label="LinkedIn profile">
          <input
            name="linkedin_url"
            type="url"
            maxLength={500}
            placeholder="https://www.linkedin.com/in/…"
            defaultValue={contact?.linkedin_url ?? ""}
            className={inputClass}
          />
        </Field>
        <Field label="Buying role">
          <select name="role" defaultValue={contact?.decision_maker_role ?? ""} className={inputClass}>
            <option value="">Not confirmed</option>
            {DECISION_MAKER_ROLES.map((r) => (
              <option key={r} value={r}>
                {label(r)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Department">
          <input name="department" maxLength={120} defaultValue={contact?.department ?? ""} className={inputClass} />
        </Field>
      </div>
      <Field label="Notes">
        <textarea name="notes" maxLength={4000} rows={2} defaultValue={contact?.notes ?? ""} className={cx(inputClass, "resize-y")} />
      </Field>
      {contact && (
        <label className="flex cursor-pointer items-center gap-2 text-[13px] text-fg-2">
          <input type="checkbox" name="verified" defaultChecked={contact.verification_status === "verified"} className="h-4 w-4" />
          Verified: someone has confirmed these details
        </label>
      )}
      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={busy} icon={contact ? <Save className="h-4 w-4" /> : <UserPlus className="h-4 w-4" />}>
          {contact ? "Save person" : "Add person"}
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
