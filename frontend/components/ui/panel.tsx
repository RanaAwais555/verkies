"use client";

import { ChevronRight } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { cx } from "@/components/ui/cx";

/**
 * A section of a page on its own surface. `primary` seats it in a machined tray: use it for the
 * one or two surfaces a page is about, not for everything. `collapsible` lets the reader fold it.
 */
export function Panel({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
  primary,
  collapsible,
  defaultOpen = true,
  testId,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  primary?: boolean;
  collapsible?: boolean;
  defaultOpen?: boolean;
  testId?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();
  const headingClass = "text-[13.5px] font-semibold tracking-[-0.005em] text-fg";
  return (
    <section
      data-testid={testId}
      className={cx("min-w-0 rounded-[14px] border border-border/80 bg-surface", primary ? "tray" : "lift", className)}
    >
      {(title || actions) && (
        <header className={cx("flex flex-wrap items-center justify-between gap-3 px-4 py-3", open && "border-b border-grid")}>
          <div className="min-w-0">
            {collapsible ? (
              // The toggle sits inside the heading, so the section keeps a real heading.
              <h2 className={headingClass}>
                <button
                  type="button"
                  onClick={() => setOpen(!open)}
                  aria-expanded={open}
                  aria-controls={bodyId}
                  className="flex items-center gap-1.5 text-left hover:text-accent-text"
                >
                  <ChevronRight aria-hidden className={cx("h-4 w-4 text-fg-3 transition-transform duration-200 ease-spring", open && "rotate-90")} />
                  {title}
                </button>
              </h2>
            ) : (
              title && <h2 className={headingClass}>{title}</h2>
            )}
            {description && <p className={cx("mt-0.5 text-xs text-fg-3", collapsible && "pl-5.5")}>{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      {open && (
        <div id={bodyId} className={cx("animate-rise p-4", bodyClassName)}>
          {children}
        </div>
      )}
    </section>
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
