import type { ReactNode } from "react";

/** A page's title row: optional Back, an eyebrow naming where you are, the title, context, actions. */
export function PageHeader({
  eyebrow,
  title,
  description,
  back,
  badges,
  actions,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  back?: ReactNode;
  badges?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="space-y-3">
      {(back || eyebrow) && (
        <div className="flex flex-wrap items-center gap-2.5">
          {back}
          {eyebrow && (
            <span className="inline-flex h-[23px] items-center rounded-full border border-[var(--hairline)] bg-[var(--tray)] px-2.5 text-[10.5px] font-medium uppercase tracking-[0.11em] text-fg-3">
              {eyebrow}
            </span>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-[21px] font-semibold tracking-[-0.018em] text-fg">{title}</h1>
            {badges}
          </div>
          {description && <div className="max-w-[72ch] text-[13.5px] text-fg-2">{description}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}
