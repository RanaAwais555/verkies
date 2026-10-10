"use client";

import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { cx } from "@/components/ui/cx";

const BASE =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium text-[13px] " +
  "transition-[background-color,color,border-color,box-shadow,transform] duration-200 ease-spring " +
  "active:scale-[0.975] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100";

const VARIANTS = {
  // Primary actions are pills; their leading icon sits in its own chip.
  primary: "h-9 rounded-full bg-accent pl-1.5 pr-4 text-accent-fg shadow-[0_8px_20px_-12px_var(--accent)] hover:bg-accent-hover",
  secondary: "h-9 rounded-[9px] border border-border-strong bg-surface-2 px-3.5 text-fg hover:border-accent/60 hover:bg-surface",
  ghost: "h-9 rounded-[9px] px-3 text-fg-2 hover:bg-sunken hover:text-fg",
  danger: "h-9 rounded-[9px] border border-bad/40 bg-bad-soft px-3.5 text-bad hover:border-bad",
};

export type ButtonVariant = keyof typeof VARIANTS;

function Content({ variant, icon, busy, children }: { variant: ButtonVariant; icon?: ReactNode; busy?: boolean; children: ReactNode }) {
  const lead = busy ? <Spinner /> : icon;
  if (variant === "primary") {
    return (
      <>
        <span className={cx("grid h-6 w-6 place-items-center rounded-full bg-white/18 transition-transform duration-300 ease-spring group-hover:translate-x-px group-hover:-translate-y-px", !lead && "hidden")}>
          {lead}
        </span>
        <span className={cx(!lead && "pl-2.5")}>{children}</span>
      </>
    );
  }
  return (
    <>
      {lead}
      {children}
    </>
  );
}

export function Button({
  variant = "secondary",
  icon,
  busy,
  className,
  children,
  ...props
}: ComponentProps<"button"> & { variant?: ButtonVariant; icon?: ReactNode; busy?: boolean }) {
  return (
    <button type="button" {...props} disabled={props.disabled || busy} className={cx("group", BASE, VARIANTS[variant], className)}>
      <Content variant={variant} icon={icon} busy={busy}>{children}</Content>
    </button>
  );
}

export function LinkButton({
  variant = "secondary",
  icon,
  className,
  children,
  ...props
}: ComponentProps<typeof Link> & { variant?: ButtonVariant; icon?: ReactNode }) {
  return (
    <Link {...props} className={cx("group", BASE, VARIANTS[variant], className)}>
      <Content variant={variant} icon={icon}>{children}</Content>
    </Link>
  );
}

/** A square button that shows only an icon. `label` names it for screen readers and the tooltip. */
export function IconButton({ label, className, children, ...props }: ComponentProps<"button"> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      {...props}
      className={cx(
        "grid h-8 w-8 shrink-0 place-items-center rounded-lg text-fg-3 transition-colors duration-200 ease-spring hover:bg-sunken hover:text-fg disabled:opacity-40",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <span aria-hidden className={cx("inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent", className)} />;
}
