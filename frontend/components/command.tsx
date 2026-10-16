"use client";

import { useRouter } from "next/navigation";
import { useDeferredValue, useEffect, useRef, useState, type KeyboardEvent } from "react";

import { Icon, type IconName } from "@/components/icons";
import { cx, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { AccountSummary, Run } from "@/lib/types";

type Item = { key: string; group: string; label: string; detail?: string; href: string; icon: IconName };

/**
 * Ctrl+K / ⌘K: jump to a page, an account or a research run by typing. Results come from the
 * same list endpoints as the pages, so each person only finds what they may see.
 */
export function CommandPalette({
  open,
  onClose,
  pages,
  accounts,
}: {
  open: boolean;
  onClose: () => void;
  pages: { href: string; label: string; icon: IconName }[];
  accounts: boolean;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const deferred = useDeferredValue(query.trim());
  const searching = deferred.length >= 2;
  const encoded = encodeURIComponent(deferred);
  const { data: accountHits, isLoading: loadingAccounts } = useApi<AccountSummary[]>(
    open && searching && accounts ? `/accounts?q=${encoded}&limit=6` : null,
  );
  const { data: runHits, isLoading: loadingRuns } = useApi<Run[]>(open && searching ? `/research-runs?q=${encoded}&limit=6` : null);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  const lower = query.trim().toLowerCase();
  const items: Item[] = [
    ...pages
      .filter((p) => !lower || p.label.toLowerCase().includes(lower))
      .map((p) => ({ key: `page-${p.href}`, group: "Pages", label: p.label, href: p.href, icon: p.icon })),
    ...(searching
      ? (accountHits ?? []).map((a) => ({
          key: `account-${a.id}`,
          group: "Accounts",
          label: a.name,
          detail: a.primary_domain ?? undefined,
          href: `/accounts/${a.id}`,
          icon: "accounts" as const,
        }))
      : []),
    ...(searching
      ? (runHits ?? []).map((r) => ({
          key: `run-${r.id}`,
          group: "Research",
          label: r.normalised_domain,
          detail: `${r.status} · ${r.review_status}`,
          href: `/research/${r.id}`,
          icon: "research" as const,
        }))
      : []),
  ];
  const current = Math.min(active, Math.max(items.length - 1, 0));

  function close() {
    setQuery("");
    setActive(0);
    onClose();
  }

  function go(item: Item | undefined) {
    if (!item) return;
    close();
    router.push(item.href);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((current + 1) % Math.max(items.length, 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((current - 1 + items.length) % Math.max(items.length, 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(items[current]);
    } else if (event.key === "Escape") {
      close();
    }
  }

  if (!open) return null;
  const groups = [...new Set(items.map((i) => i.group))];
  const loading = searching && (loadingAccounts || loadingRuns);

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-slate-950/40 px-4 pt-[12vh] backdrop-blur-[2px]" onMouseDown={close}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search VROS"
        className="w-full max-w-xl animate-[pop-in_140ms_ease-out] overflow-hidden rounded-xl border border-border bg-background shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-border px-4">
          <Icon name="research" className="h-4 w-4 text-muted" />
          <input
            ref={input}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
            placeholder="Search accounts, research and pages…"
            aria-label="Search VROS"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-results"
            aria-activedescendant={items[current] ? `command-${items[current].key}` : undefined}
            className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
          />
          {loading && <Spinner />}
          <kbd className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted">Esc</kbd>
        </div>
        <div id="command-results" role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
          {items.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-muted">
              {searching && !loading ? "Nothing matches." : "Type at least two letters to search accounts and research."}
            </p>
          )}
          {groups.map((group) => (
            <div key={group} className="mb-1">
              <p className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-muted">{group}</p>
              {items
                .filter((i) => i.group === group)
                .map((item) => {
                  const index = items.indexOf(item);
                  return (
                    <div
                      key={item.key}
                      id={`command-${item.key}`}
                      role="option"
                      aria-selected={index === current}
                      onMouseEnter={() => setActive(index)}
                      onClick={() => go(item)}
                      className={cx(
                        "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm",
                        index === current ? "bg-accent-soft text-foreground" : "text-foreground",
                      )}
                    >
                      <Icon name={item.icon} className={cx("h-4 w-4", index === current ? "text-accent" : "text-muted")} />
                      <span className="truncate font-medium">{item.label}</span>
                      {item.detail && <span className="truncate text-xs text-muted">{item.detail}</span>}
                    </div>
                  );
                })}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-4 border-t border-border px-4 py-2 text-[11px] text-muted">
          <span><kbd className="font-sans">↑↓</kbd> to move</span>
          <span><kbd className="font-sans">Enter</kbd> to open</span>
          <span className="ml-auto">Ctrl K anywhere</span>
        </div>
      </div>
    </div>
  );
}

/** Opens the palette on Ctrl+K (⌘K on a Mac). */
export function useCommandShortcut(toggle: () => void) {
  useEffect(() => {
    function onKey(event: globalThis.KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        toggle();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);
}
