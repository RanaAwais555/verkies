"use client";

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
