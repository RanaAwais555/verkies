import { defineConfig, devices } from "@playwright/test";

import { ADMIN, SITE_PORT } from "./env";

// End-to-end run of the Phase 1 checklist against the real stack: Postgres and Redis (already
// running), the API and a Celery worker from ../backend, a production build of this app, and
// local fixture websites the crawler reaches through development-only host overrides.
//
//   VROS_DATABASE_URL=... VROS_REDIS_URL=... npm run build:e2e && npm run e2e
//
// The run RESETS the configured database.

const API_PORT = 8100;
const WEB_PORT = 3100;

const backendEnv = {
  VROS_ENVIRONMENT: "development",
  VROS_PUBLIC_URL: `http://localhost:${WEB_PORT}`,
  VROS_DATABASE_URL: process.env.VROS_DATABASE_URL ?? "postgresql+psycopg://vros:vros@localhost:5432/vros",
  VROS_REDIS_URL: process.env.VROS_REDIS_URL ?? "redis://localhost:6379/0",
  VROS_STORAGE_DIR: process.env.VROS_STORAGE_DIR ?? "/tmp/vros-e2e-storage",
  VROS_FETCH_HOST_OVERRIDES: "harbour.test=127.0.0.1,pixelforge.test=127.0.0.1,oldmill.test=127.0.0.1",
  VROS_FETCH_PRIVATE_ALLOWLIST: "127.0.0.0/8",
  VROS_CRAWL_ALLOWED_PORTS: `${SITE_PORT},80,443`,
  VROS_CRAWL_MIN_INTERVAL_SECONDS: "0",
  VROS_RENDER_ENABLED: "false",
  VROS_WIKIDATA_ENABLED: "false", // no outside network in tests
  VROS_SEARCH_PROVIDER: "searxng", // answered by the fixture server
  VROS_SEARXNG_URL: `http://127.0.0.1:${SITE_PORT}`,
  VROS_ADMIN_PASSWORD: ADMIN.password,
};

export default defineConfig({
  testDir: ".",
  outputDir: "../test-results",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never", outputFolder: "../playwright-report" }]] : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
      },
    },
  ],
  webServer: [
    {
      name: "fixture sites",
      command: `uv run python -m tests.fixtures.serve ${SITE_PORT}`,
      cwd: "../../backend",
      port: SITE_PORT,
      reuseExistingServer: false,
    },
    {
      name: "api",
      command: `uv run python -m tests.fixtures.e2e_reset ${ADMIN.email} "${ADMIN.name}" && uv run uvicorn app.main:app --port ${API_PORT}`,
      cwd: "../../backend",
      env: backendEnv,
      url: `http://127.0.0.1:${API_PORT}/api/v1/health/live`,
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      name: "worker",
      command: "uv run celery -A app.workers.celery_app:celery_app worker --pool=solo --concurrency=1 --loglevel=INFO",
      cwd: "../../backend",
      env: backendEnv,
      wait: { stderr: /ready\./ },
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      name: "web",
      command: `npx next start --port ${WEB_PORT}`,
      cwd: "..",
      env: { VROS_API_INTERNAL_URL: `http://127.0.0.1:${API_PORT}` },
      url: `http://localhost:${WEB_PORT}/login`,
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
