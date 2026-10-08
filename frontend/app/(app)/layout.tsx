import { Suspense } from "react";

import { AppShell } from "@/components/shell";

// The app is client-rendered behind sign-in; the prerendered shell is just this fallback.
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <Suspense fallback={<p className="mx-auto max-w-md px-4 py-16 text-sm text-muted">Loading…</p>}>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
