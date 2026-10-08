import type { ReactNode } from "react";

/** The centred card used by the pages people see before signing in. */
export function AuthFrame({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <main className="flex flex-1 items-center justify-center px-4 py-16">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span aria-hidden className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-base font-bold text-accent-foreground">V</span>
          <span className="text-lg font-semibold tracking-tight">VROS</span>
        </div>
        <div className="rounded-xl border border-border bg-background p-6 shadow-sm">
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
        <p className="mt-6 text-center text-xs text-muted">Verkies Revenue Operating System</p>
      </div>
    </main>
  );
}
