import type { ReactNode } from "react";

import { cx } from "@/components/ui/cx";

/**
 * A data table: full width, a quiet header, rows that highlight on hover, and its own horizontal
 * scroll so a wide table never widens the page. Pages write plain <thead>/<th>/<td>.
 */
export function Table({ children, testId, className }: { children: ReactNode; testId?: string; className?: string }) {
  return (
    <div className={cx("-mx-5 -mb-4 overflow-x-auto", className)}>
      <table
        data-testid={testId}
        className={cx(
          "w-full text-left text-[13px]",
          "[&_th]:h-9 [&_th]:whitespace-nowrap [&_th]:px-5 [&_th]:text-xs [&_th]:font-medium [&_th]:text-fg-3 [&_thead]:shadow-[inset_0_-1px_0_var(--border)]",
          "[&_td]:px-5 [&_td]:py-2.5 [&_td]:align-middle [&_tbody_tr]:border-t [&_tbody_tr]:border-grid [&_tbody_tr:first-child]:border-t-0",
          "[&_tbody_tr]:transition-colors [&_tbody_tr:hover]:bg-surface-2",
        )}
      >
        {children}
      </table>
    </div>
  );
}
