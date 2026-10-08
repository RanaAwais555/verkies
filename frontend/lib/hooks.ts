"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import useSWR, { type SWRConfiguration } from "swr";

import { api, ApiError, loginPath } from "@/lib/client";
import type { Session } from "@/lib/types";

async function fetcher<T>(path: string): Promise<T> {
  try {
    return await api<T>(path);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) window.location.assign(loginPath());
    throw error;
  }
}

/** GET an API path (or nothing when `path` is null) with caching and revalidation. */
export function useApi<T>(path: string | null, config?: SWRConfiguration<T, ApiError>) {
  return useSWR<T, ApiError>(path, fetcher, config);
}

export function useSession() {
  return useApi<Session>("/auth/me", { revalidateOnFocus: false });
}

export function can(session: Session | undefined, ...permissions: string[]): boolean {
  return !!session && permissions.some((p) => session.user.permissions.includes(p));
}

/**
 * The open tab, kept in the address (`?tab=`) rather than in component state: a link opens a
 * page on its first tab, while Back and a shared link return to the tab that was open.
 */
export function useTab(first: string): [string, (key: string) => void] {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const tab = params.get("tab") ?? first;
  function setTab(key: string) {
    const next = new URLSearchParams(params);
    if (key === first) next.delete("tab");
    else next.set("tab", key);
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }
  return [tab, setTab];
}
