import { Suspense } from "react";
import { connection } from "next/server";

import { fetchReadiness } from "@/lib/api";

async function SystemStatus() {
  await connection(); // render per request: status must be live, never cached
  const readiness = await fetchReadiness();

  if (!readiness) {
    return <p className="text-sm text-red-600">API unreachable.</p>;
  }
  return (
    <ul className="space-y-1 text-sm">
      {Object.entries(readiness.checks).map(([name, check]) => (
        <li key={name} className="flex items-center gap-2">
          <span
            aria-hidden
            className={`inline-block h-2 w-2 rounded-full ${
              check.status === "ok" ? "bg-green-500" : "bg-red-500"
            }`}
          />
          <span className="capitalize">{name}</span>
          <span className="text-muted">{check.status === "ok" ? "ok" : `down (${check.error})`}</span>
        </li>
      ))}
    </ul>
  );
}

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-16">
      <h1 className="text-2xl font-semibold">Verkies Revenue Operating System</h1>
      <p className="mt-2 text-muted">
        Phase 1 is being built. Research, qualification and the CRM appear here as each slice
        ships.
      </p>
      <section className="mt-10 rounded-lg border border-border p-4">
        <h2 className="mb-3 text-sm font-medium">System status</h2>
        <Suspense fallback={<p className="text-sm text-muted">Checking…</p>}>
          <SystemStatus />
        </Suspense>
      </section>
    </main>
  );
}
