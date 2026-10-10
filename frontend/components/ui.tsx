"use client";

import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { ApiError } from "@/lib/client";

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

const BUTTON = {
  primary: "bg-accent text-accent-foreground shadow-sm hover:bg-accent-hover",
  secondary: "border border-border bg-background text-foreground shadow-sm hover:bg-surface",
  danger: "bg-red-600 text-white shadow-sm hover:bg-red-700",
  ghost: "text-muted hover:bg-surface hover:text-foreground",
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
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg px-3.5 py-2 text-sm font-medium transition-colors",
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

export function Card({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cx("rounded-xl border border-border bg-background shadow-sm", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3.5">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

/** The title row of a page: an optional Back link, the title, a line of context and actions. */
export function PageHeader({
  title,
  description,
  back,
  badges,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  back?: ReactNode;
  badges?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="space-y-2">
      {back}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            {badges}
          </div>
          {description && <div className="text-sm text-muted">{description}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}

/** A headline number. `value` is always a real count from the API, never an estimate. */
export function Stat({ label: text, value, hint, tone = "neutral" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: keyof typeof STAT_TONE }) {
  return (
    <div className="rounded-xl border border-border bg-background p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{text}</p>
      <p className={cx("mt-1 text-2xl font-semibold tabular-nums", STAT_TONE[tone])}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

const STAT_TONE = { neutral: "", accent: "text-accent", red: "text-red-600 dark:text-red-400", amber: "text-amber-600 dark:text-amber-400" };

const TONES = {
  neutral: "bg-surface text-muted ring-border",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-950/60 dark:text-emerald-300 dark:ring-emerald-400/20",
  amber: "bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-950/60 dark:text-amber-300 dark:ring-amber-400/20",
  red: "bg-red-50 text-red-700 ring-red-600/20 dark:bg-red-950/60 dark:text-red-300 dark:ring-red-400/20",
  blue: "bg-sky-50 text-sky-700 ring-sky-600/20 dark:bg-sky-950/60 dark:text-sky-300 dark:ring-sky-400/20",
  purple: "bg-violet-50 text-violet-700 ring-violet-600/20 dark:bg-violet-950/60 dark:text-violet-300 dark:ring-violet-400/20",
};

export function Badge({ tone = "neutral", children, title }: { tone?: keyof typeof TONES; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", TONES[tone])}>
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

/** Bar colour follows the value; Unknown has no bar at all. */
function barTone(value: number): string {
  if (value >= 70) return "bg-emerald-500";
  if (value >= 40) return "bg-accent";
  return "bg-slate-400 dark:bg-slate-500";
}

export function ScoreBar({ name, value }: { name: string; value: number | null | undefined }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-40 shrink-0 text-muted">{label(name)}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface">
        {value !== null && value !== undefined && (
          <div className={cx("h-2 rounded-full", barTone(value))} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
        )}
      </div>
      <Score value={value} className="w-16 text-right font-medium" />
    </div>
  );
}

export function Spinner() {
  return <span aria-hidden className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />;
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <p className="flex items-center gap-2 py-2 text-sm text-muted" role="status">
      <Spinner /> {what}…
    </p>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof ApiError || error instanceof Error ? error.message : "Something went wrong.";
  return (
    <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900/60 dark:bg-red-950/50 dark:text-red-300">
      {message}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted">{children}</p>;
}

/** A positive confirmation after an action. */
export function Success({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <p role="status" data-testid={testId} className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/50 dark:text-emerald-300">
      {children}
    </p>
  );
}

export function Field({ label: text, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="font-medium">{text}</span>
      {children}
      {hint && <span className="block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm shadow-sm outline-none transition-colors placeholder:text-muted/70 focus:border-accent focus:ring-2 focus:ring-accent/20";

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: ReactNode }[]; active: string; onChange: (key: string) => void }) {
  return (
    // The bottom line is an inset shadow, not a border with tabs overlapping it by a pixel: that
    // overlap made the row scroll vertically (a stray scrollbar on Windows).
    <div role="tablist" className="flex gap-1 overflow-x-auto overflow-y-hidden shadow-[inset_0_-1px_0_var(--border)]">
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}
          className={cx(
            "whitespace-nowrap border-b-2 px-3 py-2.5 text-sm transition-colors",
            active === t.key ? "border-accent font-medium text-foreground" : "border-transparent text-muted hover:border-border hover:text-foreground",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

/**
 * A data table inside a card: full width, quiet header, rows that highlight on hover.
 * Pages write plain <thead>/<th>/<td>; the styling lives here.
 */
export function Table({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <div className="-mx-5 -mb-5 overflow-x-auto">
      <table
        data-testid={testId}
        className={cx(
          "w-full text-left text-sm",
          "[&_thead]:bg-surface/60 [&_th]:whitespace-nowrap [&_th]:px-5 [&_th]:py-2 [&_th]:text-xs [&_th]:font-medium [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-muted",
          "[&_td]:px-5 [&_td]:py-3 [&_td]:align-top [&_tbody_tr]:border-t [&_tbody_tr]:border-border [&_tbody_tr:hover]:bg-surface/50",
        )}
      >
        {children}
      </table>
    </div>
  );
}

export function TextLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="font-medium text-accent hover:text-accent-hover hover:underline">
      {children}
    </Link>
  );
}

/** An external link to a crawled page: shown as text, never trusted as HTML. */
export function SourceLink({ url }: { url: string }) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer nofollow" className="break-all text-xs text-muted underline decoration-border underline-offset-2 hover:text-foreground">
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
