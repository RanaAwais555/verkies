import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 5.2. Earlier specs won Harbour Immigration Ltd's deal, so there is at least one outcome.
test("read the win/loss analysis", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.getByRole("link", { name: "Learning", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Win/loss analysis" })).toBeVisible();
  await page.getByRole("tab", { name: "All time" }).click();
  const overall = page.getByTestId("win-loss-overall");
  await expect(overall).toContainText(/\d+ won, \d+ lost/);
  // With only a handful of deals in the test data, groups are too small to claim a rate.
  await expect(page.getByTestId("dimension-industry")).toContainText("Too few to learn from");
});
