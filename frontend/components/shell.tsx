"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useState, type ReactNode } from "react";

import { useNavigationHistory } from "@/components/back";
import { CommandPalette, useCommandShortcut } from "@/components/command";
import { Icon, type IconName } from "@/components/icons";
import { Toaster } from "@/components/toast";
import { cx, ErrorNote, label, Loading } from "@/components/ui";
import { api } from "@/lib/client";
import { can, useSession } from "@/lib/hooks";
import { useTheme, type ThemeChoice } from "@/lib/theme";

const NAV: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Home", icon: "home" },
  { href: "/research", label: "Research", icon: "research" },
  { href: "/discover", label: "Discover", icon: "discover" },
  { href: "/accounts", label: "Accounts", icon: "accounts" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <span aria-hidden className="grid h-8 w-8 place-items-center rounded-lg bg-indigo-500 text-sm font-bold text-white">V</span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold text-white">VROS</span>
        <span className="block text-[11px] text-slate-400">Verkies Revenue OS</span>
      </span>
    </Link>
  );
}

const THEMES: { key: ThemeChoice; label: string; icon: IconName }[] = [
  { key: "light", label: "Light", icon: "sun" },
  { key: "dark", label: "Dark", icon: "moon" },
  { key: "system", label: "System", icon: "system" },
];

function ThemeSwitch() {
  const [theme, setTheme] = useTheme();
  return (
    <div role="radiogroup" aria-label="Colour theme" className="flex rounded-lg bg-white/5 p-0.5">
      {THEMES.map((t) => (
        <button
          key={t.key}
          type="button"
          role="radio"
          aria-checked={theme === t.key}
          title={`${t.label} theme`}
          onClick={() => setTheme(t.key)}
          className={cx(
            "flex flex-1 items-center justify-center gap-1.5 rounded-md py-1 text-[11px] transition-colors",
            theme === t.key ? "bg-sidebar-active text-white shadow-sm" : "text-slate-400 hover:text-white",
          )}
        >
          <Icon name={t.icon} className="h-3.5 w-3.5" />
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { data: session, error } = useSession();
  const pathname = usePathname();
  useNavigationHistory();
  const [searchOpen, setSearchOpen] = useState(false);
  const toggleSearch = useCallback(() => setSearchOpen((open) => !open), []);
  useCommandShortcut(toggleSearch);

  async function signOut() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    // A full page load, so nothing from this session (cached data, pages kept in the
    // background) is left in the tab for the next person to sign in.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- the full load is the point
    window.location.assign("/login");
  }

  if (error && error.status !== 401) {
    return (
      <main className="mx-auto max-w-md px-4 py-16">
        <ErrorNote error={error} />
      </main>
    );
  }
  if (!session) {
    return (
      <main className="mx-auto max-w-md px-4 py-16">
        <Loading what="Signing you in" />
      </main>
    );
  }
  const items = NAV.filter(
    (n) =>
      (n.href !== "/accounts" || can(session, "accounts.read", "accounts.read_own")) &&
      (n.href !== "/discover" || can(session, "research.run")),
  );
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const initials = session.user.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  return (
    <div className="flex min-h-full flex-1">
      {/* Desktop: a fixed sidebar. */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col bg-sidebar px-3 py-4 md:flex">
        <div className="px-2"><Logo /></div>
        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          className="mt-6 flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-400 transition-colors hover:border-white/20 hover:text-white"
        >
          <Icon name="research" className="h-4 w-4" />
          <span className="flex-1 text-left">Search…</span>
          <kbd className="rounded border border-white/15 px-1.5 text-[10px]">Ctrl K</kbd>
        </button>
        <nav className="mt-4 flex flex-col gap-0.5" aria-label="Main">
          {items.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              aria-current={isActive(n.href) ? "page" : undefined}
              className={cx(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                isActive(n.href) ? "bg-sidebar-active font-medium text-white" : "text-sidebar-foreground hover:bg-sidebar-active/60 hover:text-white",
              )}
            >
              <Icon name={n.icon} className={cx("h-[18px] w-[18px]", isActive(n.href) ? "text-indigo-400" : "")} />
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto space-y-4 border-t border-white/10 pt-4">
          <ThemeSwitch />
          <div className="flex items-center gap-3 px-2">
            <span aria-hidden className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-slate-700 text-xs font-semibold text-white">{initials}</span>
            <div className="min-w-0 leading-tight">
              <p className="truncate text-sm font-medium text-white" data-testid="signed-in-as">{session.user.name}</p>
              <p className="truncate text-[11px] text-slate-400">{session.user.roles.map(label).join(", ")}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={signOut}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-foreground transition-colors hover:bg-sidebar-active/60 hover:text-white"
          >
            <Icon name="signOut" className="h-[18px] w-[18px]" />
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Phones and small windows: a top bar. */}
        <header className="bg-sidebar px-4 pb-2 pt-3 md:hidden">
          <div className="flex items-center justify-between">
            <Logo />
            <button type="button" onClick={signOut} className="rounded-lg px-2.5 py-1.5 text-sm text-sidebar-foreground hover:text-white">
              Sign out
            </button>
          </div>
          <nav className="mt-3 flex gap-1 overflow-x-auto" aria-label="Main">
            {items.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                aria-current={isActive(n.href) ? "page" : undefined}
                className={cx(
                  "whitespace-nowrap rounded-lg px-3 py-1.5 text-sm",
                  isActive(n.href) ? "bg-sidebar-active font-medium text-white" : "text-sidebar-foreground",
                )}
              >
                {n.label}
              </Link>
            ))}
          </nav>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
      </div>
      <CommandPalette
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        pages={items}
        accounts={can(session, "accounts.read", "accounts.read_own")}
      />
      <Toaster />
    </div>
  );
}
