"use client";

import { Bell } from "lucide-react";
import Link from "next/link";

import { useApi } from "@/lib/hooks";

/** The top bar's way to the notifications page, with how many are unread. */
export function NotificationBell() {
  const { data } = useApi<{ unread: number }>("/notifications/count", { refreshInterval: 60_000 });
  const unread = data?.unread ?? 0;
  const label = unread > 0 ? `Notifications (${unread} unread)` : "Notifications";
  return (
    <Link
      href="/notifications"
      aria-label={label}
      title={label}
      className="relative grid h-8 w-8 shrink-0 place-items-center rounded-lg text-fg-3 transition-colors duration-200 ease-spring hover:bg-sunken hover:text-fg"
      data-testid="notification-bell"
    >
      <Bell className="h-4 w-4" />
      {unread > 0 && (
        <span className="tabular absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-semibold leading-none text-accent-fg">
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </Link>
  );
}
