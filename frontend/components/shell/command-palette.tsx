"use client";

import { CornerDownLeft, LogOut, Moon, Search, Sun, X, type LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { visibleNav } from "@/components/shell/nav";
import { useTheme } from "@/components/shell/theme";
import { cx } from "@/components/ui/cx";
import type { Session } from "@/lib/types";

type Command = { id: string; group: string; label: string; hint?: string; icon: LucideIcon; run: () => void };

/**
 * Ctrl/Cmd+K: jump to any screen, search accounts by name, change theme or sign out, without
 * leaving the keyboard. Arrow keys move, Enter runs, Escape closes.
 */
export function CommandPalette({ session, open, onClose, onSignOut }: { session: Session; open: boolean; onClose: () => void; onSignOut: () => void }) {
  const router = useRouter();
  const [theme, setTheme] = useTheme();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const go = (href: string) => () => {
      router.push(href);
      onClose();
    };
    const pages = visibleNav(session).flatMap((g) => g.items.map((i) => ({ id: i.href, group: "Go to", label: i.label, hint: g.label, icon: i.icon, run: go(i.href) })));
    return [
      ...pages,
      {
        id: "theme",
        group: "Preferences",
        label: theme === "dark" ? "Switch to light theme" : "Switch to dark theme",
        icon: theme === "dark" ? Sun : Moon,
        run: () => {
          setTheme(theme === "dark" ? "light" : "dark");
          onClose();
        },
      },
      { id: "signout", group: "Preferences", label: "Sign out", icon: LogOut, run: onSignOut },
    ];
  }, [session, theme, setTheme, router, onClose, onSignOut]);

  const q = query.trim().toLowerCase();
  const matches = commands.filter((c) => !q || c.label.toLowerCase().includes(q) || (c.hint ?? "").toLowerCase().includes(q));
  const canSearchAccounts = q.length >= 2 && session.user.permissions.some((p) => p === "accounts.read" || p === "accounts.read_own");
  const items: Command[] = canSearchAccounts
    ? [
        ...matches,
        {
          id: "search",
          group: "Search",
          label: `Search accounts for “${query.trim()}”`,
          icon: Search,
          run: () => {
            router.push(`/accounts?q=${encodeURIComponent(query.trim())}`);
            onClose();
          },
        },
      ]
    : matches;
  const active = Math.min(index, Math.max(0, items.length - 1));

  if (!open) return null;

  function onKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setIndex(Math.min(items.length - 1, active + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setIndex(Math.max(0, active - 1));
    } else if (event.key === "Enter" && items[active]) {
      event.preventDefault();
      items[active].run();
    } else if (event.key === "Escape") {
      onClose();
    }
  }

  const groups = [...new Set(items.map((i) => i.group))];
  return (
    <div className="fixed inset-0 z-50 flex animate-fade items-start justify-center bg-black/40 px-3 pt-[12vh]" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(e) => e.stopPropagation()}
        className="pop w-full max-w-[600px] animate-rise overflow-hidden rounded-2xl border border-border bg-surface"
      >
        <div className="flex h-12 items-center gap-3 border-b border-border px-4">
          <Search className="h-4 w-4 text-fg-3" />
          <input
            ref={input}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setIndex(0);
            }}
            onKeyDown={onKey}
            placeholder="Go to a screen, or search accounts…"
            aria-label="Command"
            className="h-full min-w-0 flex-1 bg-transparent text-[15px] text-fg outline-none placeholder:text-fg-3"
          />
          <button type="button" onClick={onClose} aria-label="Close the command palette" className="grid h-7 w-7 place-items-center rounded-md text-fg-3 hover:bg-sunken hover:text-fg">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[52vh] overflow-y-auto p-1.5">
          {items.length === 0 && <p className="px-3 py-6 text-center text-[13px] text-fg-3">Nothing matches “{query}”.</p>}
          {groups.map((group) => (
            <div key={group}>
              <p className="px-2.5 pb-1 pt-2.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-fg-3">{group}</p>
              {items
                .filter((i) => i.group === group)
                .map((item) => {
                  const on = items.indexOf(item) === active;
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onMouseEnter={() => setIndex(items.indexOf(item))}
                      onClick={item.run}
                      className={cx("flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left text-[13.5px]", on ? "bg-sunken text-fg" : "text-fg-2")}
                    >
                      <Icon className="h-4 w-4 shrink-0 text-fg-3" />
                      <span className="min-w-0 flex-1 truncate">{item.label}</span>
                      {item.hint && <span className="text-xs text-fg-3">{item.hint}</span>}
                      {on && <CornerDownLeft className="h-3.5 w-3.5 text-fg-3" />}
                    </button>
                  );
                })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
