import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 2.6. Runs after phase1.spec.ts and phase2-discovery.spec.ts on the same database:
// harbour.test is an approved account with a website-rebuild opportunity.
test("top leads explain their rank, and plain-English search shows how it was read", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.getByRole("link", { name: "Top Leads" }).click();
  const harbour = page.getByTestId("lead").filter({ hasText: "Harbour Immigration Ltd" });
  await expect(harbour).toBeVisible();
  await expect(harbour.getByRole("list", { name: "Why it ranks here" })).toContainText("of the priority score");

  await page.getByLabel("Describe the companies you want").fill("companies that need a website rebuild, similar to Wesbridge");
  await page.getByRole("button", { name: "Find leads" }).click();
  const readAs = page.getByTestId("interpretation");
  await expect(readAs).toContainText("website rebuild");
  await expect(readAs).toContainText("“similar to wesbridge” was not used");
  await expect(page.getByTestId("leads")).toContainText("Harbour Immigration Ltd");

  await page.getByRole("link", { name: "Duplicates" }).click();
  await expect(page.getByRole("heading", { name: "Duplicates" })).toBeVisible();
  await expect(page.getByText("No possible duplicates.")).toBeVisible();
});
