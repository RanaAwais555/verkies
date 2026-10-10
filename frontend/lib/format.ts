// Display helpers shared across screens.

const ACRONYMS: Record<string, string> = { icp: "ICP", url: "URL", seo: "SEO", crm: "CRM", mvp: "MVP", saas: "SaaS", ai: "AI", sic: "SIC" };

/** "priority_band" becomes "Priority band"; known acronyms keep their capitals. */
export function label(key: string): string {
  const words = key.split("_").map((w) => ACRONYMS[w.toLowerCase()] ?? w);
  const text = words.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

/** "3 days ago", "in 2 days", "today": for scanning lists, with the full date in a tooltip. */
export function relativeDate(value: string | null | undefined): string {
  if (!value) return "—";
  const days = Math.round((new Date(value).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  return days > 0 ? `In ${days} days` : `${-days} days ago`;
}

export function isOverdue(due: string | null | undefined): boolean {
  return !!due && new Date(due).getTime() < Date.now();
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

/** A chosen calendar date is due at the end of that working day, local time. */
export function endOfWorkingDay(date: string): string | null {
  return date ? new Date(`${date}T17:00:00`).toISOString() : null;
}

export function percent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}
