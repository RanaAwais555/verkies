"use client";

import { useSyncExternalStore } from "react";

import { cx } from "@/components/ui";

// Short confirmations after an action ("Approved", "Task done"), bottom right, gone after a few
// seconds. They add to what the page already shows and never carry the only copy of a message.

type Toast = { id: number; text: string; tone: "success" | "error" };

let toasts: Toast[] = [];
let next = 1;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function toast(text: string, tone: Toast["tone"] = "success") {
  const id = next++;
  toasts = [...toasts.slice(-3), { id, text, tone }];
  emit();
  setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id);
    emit();
  }, 4000);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const EMPTY: Toast[] = [];

export function Toaster() {
  const items = useSyncExternalStore(subscribe, () => toasts, () => EMPTY);
  return (
    <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
      {items.map((t) => (
        <div
          key={t.id}
          className={cx(
            "pointer-events-auto flex items-start gap-2.5 rounded-xl border bg-background px-4 py-3 text-sm shadow-lg",
            "animate-[toast-in_160ms_ease-out]",
            t.tone === "success" ? "border-emerald-200 dark:border-emerald-900" : "border-red-200 dark:border-red-900",
          )}
        >
          <span
            aria-hidden
            className={cx(
              "mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full text-[10px] font-bold text-white",
              t.tone === "success" ? "bg-emerald-500" : "bg-red-500",
            )}
          >
            {t.tone === "success" ? "✓" : "!"}
          </span>
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}
