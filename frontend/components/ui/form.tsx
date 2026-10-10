import type { ComponentProps, ReactNode } from "react";

import { cx } from "@/components/ui/cx";

/** A form control without a width, for filters and inline controls that set their own. */
export const controlClass =
  "rounded-[9px] border border-border-strong bg-surface-2 px-3 py-2 text-[13.5px] text-fg outline-none " +
  "placeholder:text-fg-3 transition-[border-color,box-shadow,background-color] duration-200 ease-spring " +
  "focus:border-transparent focus:bg-surface focus:shadow-[0_0_0_1px_var(--accent),0_0_0_4px_color-mix(in_srgb,var(--accent)_18%,transparent)] " +
  "disabled:cursor-not-allowed disabled:opacity-60";

/** A full-width form control, for fields in a form. */
export const inputClass = `w-full ${controlClass}`;

/** A labelled control. The label wraps the control, so clicking it focuses the input. */
export function Field({ label: text, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block space-y-1.5", className)}>
      <span className="text-[12.5px] font-medium text-fg-2">{text}</span>
      {children}
      {hint && <span className="block text-xs leading-relaxed text-fg-3">{hint}</span>}
    </label>
  );
}

export function Checkbox({ label: text, className, ...props }: ComponentProps<"input"> & { label: ReactNode }) {
  return (
    <label className={cx("flex cursor-pointer items-center gap-2 text-[13px] text-fg-2", className)}>
      <input type="checkbox" className="h-4 w-4" {...props} />
      {text}
    </label>
  );
}
