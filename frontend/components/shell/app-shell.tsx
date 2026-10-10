"use client";

import { ArrowLeft, ChevronRight, LogOut, Menu, Moon, PanelLeft, Search, Sun, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { CommandPalette } from "@/components/shell/command-palette";
import { useBack, useNavigationHistory } from "@/components/shell/history";
import { VrosLogo } from "@/components/shell/mark";
import { PageEnter } from "@/components/shell/page-enter";
import { isActive, visibleNav } from "@/components/shell/nav";
import { useTheme } from "@/components/shell/theme";
import { ErrorNote, IconButton, Loading } from "@/components/ui";
import { cx } from "@/components/ui/cx";
import { api } from "@/lib/client";
import { initials, label } from "@/lib/format";
import { useSession } from "@/lib/hooks";
import type { Session } from "@/lib/types";

async function signOut() {
  await api("/auth/logout", { method: "POST" }).catch(() => undefined);
  // A full page load, so nothing from this session (cached data, pages kept in the background)
  // is left in the tab for the next person to sign in.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- the full load is the point
  window.location.assign("/login");
}

function Sidebar({ session, collapsed, onToggle, onNavigate }: { session: Session; collapsed: boolean; onToggle: () => void; onNavigate?: () => void }) {
  const pathname = usePathname();
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const groups = visibleNav(session);
  return (
    <div className={cx("flex h-full flex-col gap-3 py-3", collapsed ? "w-[60px] px-2" : "w-[240px] px-2.5")}>
      <div className={cx("flex h-10 items-center gap-2.5", collapsed ? "justify-center" : "px-1.5")}>
        <Link href="/" onClick={onNavigate} className="flex min-w-0 items-center gap-2.5" aria-label="VROS home">
          <VrosLogo />
          {!collapsed && (
            <span className="min-w-0 leading-tight">
              <span className="block text-[14px] font-semibold tracking-[0.01em] text-fg">VROS</span>
              <span className="block truncate text-[11px] text-fg-3">Verkies workspace</span>
            </span>
          )}
        </Link>
      </div>

      <nav aria-label="Main" className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
        {groups.map((group, gi) => {
          const open = collapsed || !closed[group.key];
          return (
            <div key={group.key} className="flex flex-col gap-px">
              {collapsed ? (
                gi > 0 && <div className="mx-2 my-1.5 h-px bg-border" aria-hidden />
              ) : (
                <button
                  type="button"
                  onClick={() => setClosed({ ...closed, [group.key]: !closed[group.key] })}
                  aria-expanded={open}
                  className="flex items-center justify-between rounded-md px-2 pb-1 pt-2.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-fg-3 hover:text-fg"
                >
                  {group.label}
                  <ChevronRight className={cx("h-3.5 w-3.5 transition-transform duration-200 ease-spring", open && "rotate-90")} />
                </button>
              )}
              {open &&
                group.items.map((item) => {
                  const on = isActive(pathname, item.href);
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={on ? "page" : undefined}
                      title={collapsed ? item.label : undefined}
                      className={cx(
                        "relative flex h-9 items-center gap-2.5 rounded-lg text-[13.5px] transition-colors duration-200 ease-spring",
                        collapsed ? "justify-center" : "px-2.5",
                        on ? "bg-surface font-medium text-fg shadow-[var(--edge),0_0_0_1px_var(--border)]" : "text-fg-2 hover:bg-sunken hover:text-fg",
                      )}
                    >
                      {on && <span aria-hidden className="absolute -left-2.5 top-2 bottom-2 w-[3px] rounded-r-full bg-accent shadow-[0_0_10px_var(--accent)]" />}
                      <Icon className={cx("h-[17px] w-[17px] shrink-0", on && "text-accent-text")} />
                      {collapsed ? <span className="sr-only">{item.label}</span> : <span className="truncate">{item.label}</span>}
                    </Link>
                  );
                })}
            </div>
          );
        })}
      </nav>

      <div className={cx("flex items-center gap-2.5 rounded-[11px] border border-border bg-surface/60 p-2", collapsed && "flex-col")}>
        <span aria-hidden className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent-text">
          {initials(session.user.name)}
        </span>
        <div className={cx("min-w-0 flex-1 leading-tight", collapsed && "sr-only")}>
          <p className="truncate text-[13px] font-medium text-fg" data-testid="signed-in-as">{session.user.name}</p>
          <p className="truncate text-[11px] text-fg-3">{session.user.roles.map(label).join(", ")}</p>
        </div>
        <IconButton label="Sign out" onClick={signOut}>
          <LogOut className="h-4 w-4" />
        </IconButton>
      </div>
      <button
        type="button"
        onClick={onToggle}
        className={cx("hidden h-8 items-center gap-2.5 rounded-lg text-[12.5px] text-fg-3 hover:bg-sunken hover:text-fg md:flex", collapsed ? "justify-center" : "px-2.5")}
      >
        <PanelLeft className="h-4 w-4" />
        {collapsed ? <span className="sr-only">Expand sidebar</span> : "Collapse sidebar"}
      </button>
    </div>
  );
}

function TopBar({ onMenu, onPalette }: { onMenu: () => void; onPalette: () => void }) {
  const back = useBack();
  const [theme, setTheme] = useTheme();
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border bg-[color-mix(in_srgb,var(--surface)_82%,transparent)] px-3 backdrop-blur-md md:px-5">
      <IconButton label="Open the menu" onClick={onMenu} className="md:hidden">
        <Menu className="h-4 w-4" />
      </IconButton>
      <button
        type="button"
        onClick={back.goBack}
        disabled={!back.canGoBack}
        aria-label="Back"
        title={back.canGoBack ? "Back" : "Nothing to go back to"}
        className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] text-fg-2 transition-colors hover:bg-sunken hover:text-fg disabled:opacity-40 disabled:hover:bg-transparent"
      >
        <ArrowLeft className="h-4 w-4" />
        <span className="hidden sm:inline">Back</span>
      </button>
      <button
        type="button"
        onClick={onPalette}
        className="flex h-9 min-w-0 max-w-md flex-1 items-center gap-2.5 rounded-[10px] border border-border bg-surface-2 px-3 text-left text-[13px] text-fg-3 transition-colors hover:border-border-strong"
      >
        <Search className="h-4 w-4 shrink-0" />
        <span className="truncate">Jump to a screen or find an account…</span>
        <kbd className="ml-auto hidden rounded border border-border-strong border-b-2 bg-surface px-1.5 font-mono text-[10.5px] text-fg-2 sm:inline">Ctrl K</kbd>
      </button>
      <span className="flex-1" />
      <IconButton label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
        {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </IconButton>
    </header>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: session, error } = useSession();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [palette, setPalette] = useState(false);
  useNavigationHistory();

  const closePalette = useCallback(() => setPalette(false), []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette((open) => !open);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (error && error.status !== 401) {
    return (
      <main className="mx-auto max-w-md px-4 py-16">
        <ErrorNote error={error} />
      </main>
    );
  }
  if (!session) {
    return (
      <main className="mx-auto flex max-w-md justify-center px-4 py-16">
        <Loading what="Signing you in" />
      </main>
    );
  }

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen shrink-0 border-r border-border bg-sidebar/80 md:block">
        <Sidebar session={session} collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button type="button" aria-label="Close the menu" className="absolute inset-0 animate-fade bg-black/40" onClick={() => setMobileOpen(false)} />
          <aside className="pop absolute inset-y-0 left-0 animate-slide-in border-r border-border bg-sidebar">
            <div className="absolute right-2 top-3">
              <IconButton label="Close the menu" onClick={() => setMobileOpen(false)}>
                <X className="h-4 w-4" />
              </IconButton>
            </div>
            <Sidebar session={session} collapsed={false} onToggle={() => undefined} onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenu={() => setMobileOpen(true)} onPalette={() => setPalette(true)} />
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-7 md:py-7">
          <PageEnter key={pathname}>{children}</PageEnter>
        </main>
      </div>

      <CommandPalette session={session} open={palette} onClose={closePalette} onSignOut={signOut} />
    </div>
  );
}
