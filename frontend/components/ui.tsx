"use client";

import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { ApiError } from "@/lib/client";

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

const BUTTON = {
  primary: "bg-foreground text-background hover:opacity-90",
  secondary: "border border-border hover:bg-surface",
  danger: "bg-red-600 text-white hover:bg-red-700",
  ghost: "hover:bg-surface",
};

export function Button({
  variant = "primary",
  className,
  busy,
  children,
  ...props
}: ComponentProps<"button"> & { variant?: keyof typeof BUTTON; busy?: boolean }) {
  return (
    <button
      {...props}
      disabled={props.disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium",
        "disabled:cursor-not-allowed disabled:opacity-50",
        BUTTON[variant],
        className,
      )}
    >
      {busy && <Spinner />}
      {children}
    </button>
  );
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-lg border border-border bg-background p-4", className)}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

const TONES = {
  neutral: "bg-surface text-foreground",
  green: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
  amber: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  red: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  blue: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  purple: "bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300",
};

export function Badge({ tone = "neutral", children, title }: { tone?: keyof typeof TONES; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium", TONES[tone])}>
      {children}
    </span>
  );
}

const BAND_TONE: Record<string, keyof typeof TONES> = {
  hot: "red",
  high: "amber",
  qualified: "green",
  monitor: "blue",
  reject: "neutral",
};

export function BandBadge({ band }: { band: string | null }) {
  // Prefixed so a band never reads like an action ("Reject" next to Approve/Reject buttons).
  if (!band) return <Badge title="Priority band: Unknown">Band: Unknown</Badge>;
  return (
    <Badge tone={BAND_TONE[band] ?? "neutral"} title="Priority band from the score">
      Band: {label(band)}
    </Badge>
  );
}

const STATUS_TONE: Record<string, keyof typeof TONES> = {
  queued: "neutral",
  running: "blue",
  retrying: "blue",
  completed: "green",
  failed: "red",
  cancelled: "neutral",
  pending: "amber",
  approved: "green",
  rejected: "red",
  open: "blue",
  in_progress: "blue",
  done: "green",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{label(status)}</Badge>;
}

/** A 0-100 score. Null is Unknown (no evidence), never zero. */
export function Score({ value, className }: { value: number | null | undefined; className?: string }) {
  if (value === null || value === undefined) {
    return <span className={cx("text-muted", className)} title="Unknown: no evidence">Unknown</span>;
  }
  return <span className={cx("tabular-nums", className)}>{Math.round(value)}</span>;
}

export function ScoreBar({ name, value }: { name: string; value: number | null | undefined }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-40 shrink-0 text-muted">{label(name)}</span>
      <div className="h-1.5 flex-1 rounded bg-surface">
        {value !== null && value !== undefined && (
          <div className="h-1.5 rounded bg-foreground" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
        )}
      </div>
      <Score value={value} className="w-16 text-right" />
    </div>
  );
}

export function Spinner() {
  return <span aria-hidden className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />;
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <p className="flex items-center gap-2 text-sm text-muted" role="status">
      <Spinner /> {what}…
    </p>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof ApiError || error instanceof Error ? error.message : "Something went wrong.";
  return (
    <p role="alert" className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
      {message}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}

export function Field({ label: text, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="font-medium">{text}</span>
      {children}
      {hint && <span className="block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-foreground";

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: ReactNode }[]; active: string; onChange: (key: string) => void }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-border">
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}
          className={cx(
            "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm",
            active === t.key ? "border-foreground font-medium" : "border-transparent text-muted hover:text-foreground",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function TextLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="underline decoration-border underline-offset-2 hover:decoration-foreground">
      {children}
    </Link>
  );
}

/** An external link to a crawled page: shown as text, never trusted as HTML. */
export function SourceLink({ url }: { url: string }) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer nofollow" className="break-all text-xs text-muted underline underline-offset-2">
      {url}
    </a>
  );
}

const ACRONYMS: Record<string, string> = { icp: "ICP", url: "URL", seo: "SEO", crm: "CRM", mvp: "MVP", saas: "SaaS", ai: "AI" };

export function label(key: string): string {
  const words = key.split("_").map((w) => ACRONYMS[w.toLowerCase()] ?? w);
  const text = words.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "—";
  const date = new Date(value);
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function isOverdue(due: string | null): boolean {
  return !!due && new Date(due).getTime() < Date.now();
}
