"use client";

import { mutate } from "swr";

// Browser-side access to the VROS API. Every request goes to /api on the same origin (Caddy in
// Docker, a rewrite in `npm run dev`), carries the session cookie, and echoes the CSRF token in a
// header on every state-changing request: the double-submit pattern in backend/app/auth/deps.py.

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown> | undefined;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const CSRF_COOKIES = ["__Host-vros_csrf", "vros_csrf"];

function csrfToken(): string {
  for (const name of CSRF_COOKIES) {
    const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
    if (match) return decodeURIComponent(match.slice(name.length + 1));
  }
  return "";
}

/** Where to send someone whose session has ended, bringing them back here afterwards. */
export function loginPath(): string {
  const here = window.location.pathname + window.location.search;
  return here.startsWith("/login") ? "/login" : `/login?next=${encodeURIComponent(here)}`;
}

type Params = Record<string, string | number | boolean | undefined | null>;
type Options = { method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"; body?: unknown; params?: Params };

/** Build an API path with a query string, dropping empty values. */
export function withQuery(path: string, params: Params = {}): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  return query.size ? `${path}?${query}` : path;
}

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();

  let response: Response;
  try {
    response = await fetch(`/api/v1${withQuery(path, options.params)}`, {
      method,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(0, "network", "Cannot reach the server. Check your connection and try again.");
  }

  const data = response.status === 204 ? undefined : await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error;
    if (error) throw new ApiError(response.status, error.code, error.message, error.details);
    // FastAPI request validation errors arrive as {"detail": [...]}.
    const detail = Array.isArray(data?.detail) ? data.detail.map((d: { msg: string }) => d.msg).join("; ") : null;
    throw new ApiError(response.status, "invalid", detail ?? `The request failed (${response.status}).`);
  }

  // A change on one screen can show on others: completing a task changes "requires attention",
  // an approval adds an account. Refetch everything on screen. Not for /auth: sign-in, sign-out
  // and accepting an invite navigate away, and inspecting an invite is itself an on-screen fetch.
  if (method !== "GET" && !path.startsWith("/auth/")) void mutate(() => true);
  return data as T;
}
