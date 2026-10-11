"use client";

import { ArrowRight, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useId, useState, type ReactNode } from "react";

import { cx } from "@/components/ui/cx";

/**
 * A card: one section of a page on its own surface, like a section of a LinkedIn profile. A clear
 * title, the content below it, and an optional full-width footer (usually "Show all →").
 * `collapsible` lets the reader fold it. Every card looks the same, so pages read as one stack.
 */
export function Panel({
  title,
  description,
  actions,
  children,
  footer,
  className,
  bodyClassName,
  collapsible,
  defaultOpen = true,
  testId,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  bodyClassName?: string;
  /** Kept for call sites written before every card looked alike; it no longer changes the look. */
  primary?: boolean;
  collapsible?: boolean;
  defaultOpen?: boolean;
  testId?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();
  const headingClass = "text-[16px] font-semibold tracking-[-0.012em] text-fg";
  return (
    <section data-testid={testId} className={cx("lift min-w-0 overflow-hidden rounded-xl border border-border/80 bg-surface", className)}>
      {(title || actions) && (
        <header className={cx("flex flex-wrap items-start justify-between gap-3 px-5 pt-4", open ? "pb-1" : "pb-4")}>
          <div className="min-w-0">
            {collapsible ? (
              // The toggle sits inside the heading, so the section keeps a real heading.
              <h2 className={headingClass}>
                <button
                  type="button"
                  onClick={() => setOpen(!open)}
                  aria-expanded={open}
                  aria-controls={bodyId}
                  className="-ml-1 flex items-center gap-1 text-left hover:text-accent-text"
                >
                  <ChevronRight aria-hidden className={cx("h-4 w-4 text-fg-3 transition-transform duration-200 ease-spring", open && "rotate-90")} />
                  {title}
                </button>
              </h2>
            ) : (
              title && <h2 className={headingClass}>{title}</h2>
            )}
            {description && <p className={cx("mt-0.5 text-[12.5px] text-fg-3", collapsible && "pl-4")}>{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      {open && (
        <>
          <div id={bodyId} className={cx("animate-rise px-5 pb-4", title || actions ? "pt-3" : "pt-4", bodyClassName)}>
            {children}
          </div>
          {footer && <div className="border-t border-grid">{footer}</div>}
        </>
      )}
    </section>
  );
}

const showAllClass =
  "flex w-full items-center justify-center gap-1.5 py-3 text-[13px] font-medium text-fg-2 transition-colors duration-200 ease-spring hover:bg-surface-2 hover:text-fg";

/** A card's "Show all →" footer: a link to the full list, or a button that expands it in place. */
export function ShowAll({ children, href, onClick, expanded }: { children: ReactNode; href?: string; onClick?: () => void; expanded?: boolean }) {
  const arrow = <ArrowRight aria-hidden className="h-4 w-4" />;
  if (href)
    return (
      <Link href={href} className={showAllClass}>
        {children}
        {arrow}
      </Link>
    );
  return (
    <button type="button" onClick={onClick} aria-expanded={expanded} className={showAllClass}>
      {children}
      {/* Expanding in place gets a chevron; going somewhere else (another tab) gets the arrow. */}
      {expanded === undefined ? arrow : <ChevronRight aria-hidden className={cx("h-4 w-4 transition-transform duration-200 ease-spring", expanded ? "-rotate-90" : "rotate-90")} />}
    </button>
  );
}

/** A quiet in-page group: a heading and a rule, no surface. For hierarchy without another box. */
export function Section({ title, aside, children, className }: { title: ReactNode; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("min-w-0 space-y-3", className)}>
      <div className="flex items-center justify-between gap-3 border-b border-grid pb-2">
        <h2 className="text-[13.5px] font-semibold text-fg">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
