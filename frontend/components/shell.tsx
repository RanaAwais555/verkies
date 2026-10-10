"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useNavigationHistory } from "@/components/back";
import { Icon, type IconName } from "@/components/icons";
import { cx, ErrorNote, label, Loading } from "@/components/ui";
import { api } from "@/lib/client";
import { can, useSession } from "@/lib/hooks";

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

export function AppShell({ children }: { children: ReactNode }) {
  const { data: session, error } = useSession();
  const pathname = usePathname();
  useNavigationHistory();

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
        <nav className="mt-8 flex flex-col gap-0.5" aria-label="Main">
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
        <div className="mt-auto border-t border-white/10 pt-4">
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
            className="mt-3 flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-foreground transition-colors hover:bg-sidebar-active/60 hover:text-white"
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
    </div>
  );
}
