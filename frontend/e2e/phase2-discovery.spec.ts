import { expect, test } from "@playwright/test";

import { ADMIN, SITE_PORT } from "./env";

// Runs after phase1.spec.ts on the same database: harbour.test is an account by now and
// pixelforge.test was researched and rejected.
test("import a CSV, see every row checked, and research the new ones", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.getByRole("link", { name: "Discover" }).click();
  const csv = [
    "Company,Website,Sector",
    `Old Mill Bakery,http://oldmill.test:${SITE_PORT}/,Food`,
    `Harbour,http://harbour.test:${SITE_PORT}/,Legal`,
    `Pixelforge,http://pixelforge.test:${SITE_PORT}/,Agency`,
    "Nowhere,not a website,",
  ].join("\n");
  await page.getByLabel("CSV file").setInputFiles({ name: "prospects.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByRole("heading", { name: "prospects.csv" })).toBeVisible();

  // The columns were recognised from the header; checking sorts every row.
  await expect(page.getByLabel("Website (required)")).toHaveValue("Website");
  await page.getByRole("button", { name: "Check rows" }).click();
  const rows = page.getByTestId("import-rows");
  await expect(rows.locator("tr", { hasText: "oldmill.test" })).toContainText("New");
  await expect(rows.locator("tr", { hasText: "harbour.test" })).toContainText("Existing account");
  await expect(rows.locator("tr", { hasText: "pixelforge.test" })).toContainText("Already researched");
  await expect(rows.locator("tr", { hasText: "not a website" })).toContainText("Invalid");

  await page.getByRole("button", { name: /^Select new/ }).click();
  await page.getByRole("button", { name: "Research selected (1)" }).click();
  await expect(page.getByTestId("research-result")).toContainText("Started research on 1 company");
  const row = rows.locator("tr", { hasText: "oldmill.test" });
  await expect(row).toContainText("Queued");
  await row.getByRole("link", { name: "Open" }).click();

  // It goes through the normal research and review flow; a closed business is flagged.
  await expect(page.getByRole("tab", { name: "Lead brief" })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("brief").getByText("Does not qualify")).toBeVisible();

  await page.goto("/discover");
  await expect(page.getByTestId("imports")).toContainText("prospects.csv");
});

test("search the web: results are checked like an import", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.goto("/discover");
  await page.getByLabel("Search query").fill("immigration advisers in London");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Search: immigration advisers in London" })).toBeVisible();
  const rows = page.getByTestId("import-rows");
  await expect(rows.locator("tr", { hasText: "harbour.test" })).toContainText("Existing account");
  await expect(rows.locator("tr", { hasText: "pixelforge.test" })).toContainText("Already researched");
  await expect(rows).not.toContainText("linkedin");
  await expect(page.getByText("Which column is which?")).toHaveCount(0);
});
