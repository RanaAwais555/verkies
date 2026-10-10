"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useId, type ReactNode } from "react";

import { cx } from "@/components/ui/cx";

export type TabDef = { key: string; label: ReactNode };

export function Tabs({
  tabs,
  active,
  onChange,
  label = "Sections",
  className,
}: {
  tabs: TabDef[];
  active: string;
  onChange: (key: string) => void;
  label?: string;
  className?: string;
}) {
  // One indicator per tab row slides between tabs; the id keeps rows on the same page independent.
  const group = useId();
  const still = useReducedMotion();
  return (
    // The rule under the row is an inset shadow rather than a border the tabs overlap by a pixel;
    // that overlap made the row scroll vertically and showed a stray scrollbar on Windows.
    <div role="tablist" aria-label={label} className={cx("flex gap-1 overflow-x-auto overflow-y-hidden shadow-[inset_0_-1px_0_var(--border)]", className)}>
      {tabs.map((t) => {
        const on = active === t.key;
        return (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(t.key)}
            className={cx(
              "relative whitespace-nowrap px-3 py-2.5 text-[13px] transition-colors duration-200 ease-spring",
              on ? "font-medium text-fg" : "text-fg-3 hover:text-fg",
            )}
          >
            {t.label}
            {on && (
              <motion.span
                aria-hidden
                layoutId={`tab-${group}`}
                transition={still ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 40 }}
                className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-accent shadow-[0_0_8px_var(--accent)]"
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
