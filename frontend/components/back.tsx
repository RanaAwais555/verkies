"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Icon } from "@/components/icons";

// The pages visited in this tab since the app loaded, so Back can return to the page someone
// came from, or to a sensible list page when they opened a link directly.
const visited: string[] = [];

/** Record in-app navigation. Mounted once, in the app shell. */
export function useNavigationHistory() {
  const pathname = usePathname();
  useEffect(() => {
    if (visited.at(-1) === pathname) return;
    if (visited.at(-2) === pathname) visited.pop(); // went back
    else visited.push(pathname);
  }, [pathname]);
}

/** Back to the previous page in the app, or to `fallback` when this page was opened directly. */
export function BackLink({ fallback }: { fallback: string }) {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => (visited.length > 1 ? router.back() : router.push(fallback))}
      className="-ml-1 inline-flex items-center gap-1 rounded-md px-1 py-0.5 text-sm text-muted transition-colors hover:text-foreground"
      data-testid="back"
    >
      <Icon name="back" /> Back
    </button>
  );
}
