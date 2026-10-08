"use client";

// Browser-side API access. Everything goes to /api on the same origin (Caddy in Docker, a
// rewrite in `npm run dev`), with the session cookie, and the CSRF token echoed in a header on
// every state-changing request (double submit, see backend/app/auth/deps.py).

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

function csrfToken(): string {
  for (const name of ["__Host-vros_csrf", "vros_csrf"]) {
    const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
    if (match) return decodeURIComponent(match.slice(name.length + 1));
  }
  return "";
}

export function loginPath(): string {
  const here = window.location.pathname + window.location.search;
  return here.startsWith("/login") ? "/login" : `/login?next=${encodeURIComponent(here)}`;
}

type Options = { method?: string; body?: unknown; params?: Record<string, string | number | boolean | undefined | null> };

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const method = options.method ?? "GET";
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const url = `/api/v1${path}${query.size ? `?${query}` : ""}`;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(0, "network", "Cannot reach the server. Check your connection.");
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error;
    if (error) throw new ApiError(response.status, error.code, error.message, error.details);
    // FastAPI request validation errors use {"detail": [...]}.
    const detail = Array.isArray(data?.detail) ? data.detail.map((d: { msg: string }) => d.msg).join("; ") : null;
    throw new ApiError(response.status, "invalid", detail ?? `Request failed (${response.status}).`);
  }
  return data as T;
}
