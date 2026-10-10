import { Suspense } from "react";

import { AppShell } from "@/components/shell/app-shell";

// Everything behind sign-in renders in the browser; the prerendered shell is only this fallback.
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <Suspense fallback={<p className="mx-auto max-w-md px-4 py-16 text-sm text-fg-3">Loading…</p>}>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
