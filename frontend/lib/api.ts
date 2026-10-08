// Server-side base URL for the API. Inside Docker this is the internal service address;
// browsers never use it (they call /api on the public origin).
export function apiInternalUrl(): string {
  return process.env.VROS_API_INTERNAL_URL ?? "http://localhost:8000";
}

export type CheckResult = { status: "ok" | "down"; error: string | null };
export type Readiness = { status: "ok" | "down"; checks: Record<string, CheckResult> };

export async function fetchReadiness(): Promise<Readiness | null> {
  try {
    const response = await fetch(`${apiInternalUrl()}/api/v1/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    // 503 still carries the per-check body.
    if (response.status !== 200 && response.status !== 503) return null;
    return (await response.json()) as Readiness;
  } catch {
    return null;
  }
}
