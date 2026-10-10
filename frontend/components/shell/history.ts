"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";

import { parentOf } from "@/components/shell/nav";

// The pages visited in this tab since the app loaded. Back returns to where someone came from, or
// to the page's parent list when they opened a link directly.
let visited: string[] = [];
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

/** Record in-app navigation. Mounted once, in the app shell. */
export function useNavigationHistory() {
  const pathname = usePathname();
  useEffect(() => {
    if (visited.at(-1) === pathname) return;
    if (visited.at(-2) === pathname) visited = visited.slice(0, -1); // went back
    else visited = [...visited, pathname];
    emit();
  }, [pathname]);
}

export function useBack(): { canGoBack: boolean; goBack: () => void; label: string } {
  const router = useRouter();
  const pathname = usePathname();
  const depth = useSyncExternalStore(subscribe, () => visited.length, () => 0);
  const parent = parentOf(pathname);
  const canGoBack = depth > 1 || parent !== null;
  return {
    canGoBack,
    label: depth > 1 ? "Back" : parent ? "Back" : "Nothing to go back to",
    goBack: () => {
      if (depth > 1) router.back();
      else if (parent) router.push(parent);
    },
  };
}
