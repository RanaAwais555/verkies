"use client";

import { useSyncExternalStore } from "react";

export type Theme = "dark" | "light";

const listeners = new Set<() => void>();

function current(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

/** The active theme, set before paint by app/layout.tsx, and a way to change it. */
export function useTheme(): [Theme, (next: Theme) => void] {
  const theme = useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    current,
    () => "dark" as Theme,
  );
  function setTheme(next: Theme) {
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("vros-theme", next);
    } catch {
      // Storage can be blocked (private windows); the change still applies for this page.
    }
    for (const l of listeners) l();
  }
  return [theme, setTheme];
}
