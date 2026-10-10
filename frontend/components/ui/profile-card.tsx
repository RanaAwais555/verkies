import type { ReactNode } from "react";

import { cx } from "@/components/ui/cx";

/**
 * The card at the top of a record, like a LinkedIn profile or company page: a cover band, the
 * record's tile overlapping it, the name, a one-line tagline, a meta line, actions, and the
 * record's tabs along the bottom edge.
 */
export function ProfileCard({
  tile,
  title,
  badges,
  tagline,
  meta,
  actions,
  tabs,
  round,
}: {
  tile: ReactNode;
  title: ReactNode;
  badges?: ReactNode;
  tagline?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  /** Usually a <Tabs> row; it sits flush along the bottom of the card. */
  tabs?: ReactNode;
  /** A person gets a round tile; a company a rounded square. */
  round?: boolean;
}) {
  return (
    <section className="lift min-w-0 overflow-hidden rounded-xl border border-border/80 bg-surface">
      {/* The cover: the accent wash with the technical grid, the same atmosphere as the page. */}
      <div
        aria-hidden
        className="h-20 sm:h-24"
        style={{
          background:
            "radial-gradient(420px 160px at 82% 0%, color-mix(in srgb, var(--violet) 34%, transparent), transparent 70%), " +
            "radial-gradient(520px 200px at 12% 120%, color-mix(in srgb, var(--accent) 42%, transparent), transparent 72%), " +
            "repeating-linear-gradient(to right, var(--gridline) 0 1px, transparent 1px 28px), " +
            "repeating-linear-gradient(to bottom, var(--gridline) 0 1px, transparent 1px 28px), " +
            "color-mix(in srgb, var(--accent) 10%, var(--surface-2))",
        }}
      />
      <div className="px-5 pb-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div
            className={cx(
              "-mt-10 grid h-[76px] w-[76px] shrink-0 place-items-center border-4 border-surface bg-accent-soft text-[22px] font-semibold text-accent-text shadow-[var(--lift)] sm:-mt-12 sm:h-[88px] sm:w-[88px]",
              round ? "rounded-full" : "rounded-2xl",
            )}
          >
            {tile}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2 pt-3">{actions}</div>}
        </div>
        <div className="mt-3 min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="min-w-0 break-words text-[22px] font-semibold leading-tight tracking-[-0.02em] text-fg">{title}</h1>
            {badges}
          </div>
          {tagline && <p className="line-clamp-2 max-w-[80ch] text-[14px] text-fg-2">{tagline}</p>}
          {meta && <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-0.5 text-[13px] text-fg-3">{meta}</div>}
        </div>
      </div>
      {tabs && <div className="border-t border-grid px-3 [&_[role=tablist]]:shadow-none">{tabs}</div>}
    </section>
  );
}
