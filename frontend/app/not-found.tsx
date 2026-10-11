import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { VrosLogo } from "@/components/shell/mark";

export const metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <main className="grid min-h-[100dvh] place-items-center px-4">
      <div className="tray max-w-md space-y-4 p-8 text-center">
        <div className="flex justify-center">
          <VrosLogo size="lg" />
        </div>
        <p className="font-mono text-xs uppercase tracking-[0.14em] text-fg-3">404</p>
        <h1 className="text-xl font-semibold tracking-[-0.015em] text-fg">This page does not exist</h1>
        <p className="text-[13.5px] text-fg-2">The link may be old, or the record may have been removed. Nothing was changed.</p>
        <Link
          href="/"
          className="inline-flex h-9 items-center gap-2 rounded-full bg-accent px-4 text-[13px] font-medium text-accent-fg transition-colors hover:bg-accent-hover"
        >
          <ArrowLeft aria-hidden className="h-4 w-4" />
          Go to Command Center
        </Link>
      </div>
    </main>
  );
}
