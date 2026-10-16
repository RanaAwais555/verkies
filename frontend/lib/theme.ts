"use client";

import { useEffect, useSyncExternalStore } from "react";

import { THEME_KEY as KEY } from "@/lib/theme-script";

// The colour theme: light, dark, or follow the system. The choice is a per-browser convenience
// kept in localStorage; <html data-theme> holds the resolved theme the CSS reads.

export type ThemeChoice = "light" | "dark" | "system";

const CHANGED = "vros-theme-change";

function read(): ThemeChoice {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

function apply(choice: ThemeChoice) {
  const dark = choice === "dark" || (choice === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGED, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGED, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const choice = useSyncExternalStore(subscribe, read, () => "system" as const);

  // Follow the system setting live while the choice is "system".
  useEffect(() => {
    apply(choice);
    if (choice !== "system") return;
    const media = matchMedia("(prefers-color-scheme: dark)");
    const follow = () => apply("system");
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, [choice]);

  function set(next: ThemeChoice) {
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // Storage blocked (private mode): the theme still applies for this page.
    }
    apply(next);
    window.dispatchEvent(new Event(CHANGED));
  }
  return [choice, set];
}
