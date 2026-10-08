"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useNavigationHistory } from "@/components/back";
import { Button, cx, ErrorNote, Loading } from "@/components/ui";
import { api } from "@/lib/client";
import { can, useSession } from "@/lib/hooks";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/research", label: "Research" },
  { href: "/discover", label: "Discover" },
  { href: "/accounts", label: "Accounts" },
  { href: "/settings", label: "Settings" },
];

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
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-border">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-4 px-4 py-2">
          <Link href="/" className="font-semibold">VROS</Link>
          <nav className="flex flex-1 gap-1 overflow-x-auto">
            {NAV.filter(
              (n) =>
                (n.href !== "/accounts" || can(session, "accounts.read", "accounts.read_own")) &&
                (n.href !== "/discover" || can(session, "research.run")),
            ).map((n) => {
              const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={active ? "page" : undefined}
                  className={cx("rounded-md px-2.5 py-1 text-sm", active ? "bg-surface font-medium" : "text-muted hover:text-foreground")}
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>
          <span className="hidden text-sm text-muted sm:inline" data-testid="signed-in-as">{session.user.name}</span>
          <Button variant="ghost" onClick={signOut}>Sign out</Button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
    </div>
  );
}
