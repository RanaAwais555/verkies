import {
  BarChart3,
  Bell,
  Bookmark,
  Building2,
  Columns3,
  Compass,
  FolderKanban,
  HeartPulse,
  GitMerge,
  Handshake,
  LayoutDashboard,
  Send,
  Settings,
  Sparkles,
  SquareCheckBig,
  Target,
  type LucideIcon,
} from "lucide-react";

import { can } from "@/lib/hooks";
import type { Session } from "@/lib/types";

export type NavItem = { href: string; label: string; icon: LucideIcon; needs?: string[] };
export type NavGroup = { key: string; label: string; items: NavItem[] };

const ACCOUNTS = ["accounts.read", "accounts.read_own"];

// Only screens the API supports today. A role sees an item when it holds any listed permission;
// the API enforces the same rules, so hiding an item is a convenience, not access control.
export const NAV: NavGroup[] = [
  {
    key: "revenue",
    label: "Revenue",
    items: [
      { href: "/", label: "Command Center", icon: LayoutDashboard },
      { href: "/discover", label: "Discover", icon: Compass, needs: ["research.run"] },
      { href: "/research", label: "Lead Intelligence", icon: Sparkles },
      { href: "/leads", label: "Top Leads", icon: Target, needs: ACCOUNTS },
      { href: "/accounts", label: "Accounts", icon: Building2, needs: ACCOUNTS },
      { href: "/pipeline", label: "Pipeline", icon: Columns3, needs: ACCOUNTS },
      { href: "/outreach", label: "Outreach", icon: Send, needs: ACCOUNTS },
      { href: "/reports", label: "Reports", icon: BarChart3, needs: [...ACCOUNTS, "prospects.review", "reports.team"] },
    ],
  },
  {
    key: "workspace",
    label: "Workspace",
    items: [
      { href: "/tasks", label: "Tasks", icon: SquareCheckBig, needs: ACCOUNTS },
      { href: "/clients", label: "Clients", icon: HeartPulse, needs: ACCOUNTS },
      { href: "/projects", label: "Projects", icon: FolderKanban, needs: ACCOUNTS },
      { href: "/referrals", label: "Referrals", icon: Handshake, needs: ACCOUNTS },
      { href: "/follow-ups", label: "Follow-ups", icon: Bell, needs: ACCOUNTS },
      { href: "/views", label: "Saved views", icon: Bookmark, needs: ACCOUNTS },
    ],
  },
  {
    key: "management",
    label: "Management",
    items: [
      { href: "/duplicates", label: "Duplicates", icon: GitMerge, needs: ["accounts.merge"] },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export function visibleNav(session: Session): NavGroup[] {
  return NAV.map((g) => ({ ...g, items: g.items.filter((i) => !i.needs || can(session, ...i.needs)) })).filter((g) => g.items.length > 0);
}

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

/** The list page a detail page belongs to: where Back goes when there is no history. */
export function parentOf(pathname: string): string | null {
  if (pathname === "/") return null;
  const parts = pathname.split("/").filter(Boolean);
  return parts.length > 1 ? `/${parts.slice(0, -1).join("/")}` : "/";
}
