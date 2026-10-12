import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 6.1. Harbour Immigration Ltd exists from the earlier specs. What a check finds depends on
// the fixture site's sources, so this covers watching, queueing a check and the Monitoring page.
test("watch an account and see it on the Monitoring page", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.goto("/accounts");
  await page.getByLabel("Search accounts").fill("harbour");
  await page.getByTestId("accounts").getByRole("link", { name: "Harbour Immigration Ltd" }).click();
  await page.getByRole("button", { name: "Watch", exact: true }).click();
  await expect(page.getByRole("button", { name: "Stop watching" })).toBeVisible();
  await page.getByRole("button", { name: "Check now" }).click();
  await expect(page.getByRole("button", { name: "Check queued" })).toBeVisible();
  await expect(page.getByTestId("account-monitoring")).toBeVisible();

  await page.getByRole("link", { name: "Monitoring", exact: true }).click();
  await expect(page.getByTestId("watched-row").filter({ hasText: "Harbour Immigration Ltd" })).toBeVisible();
  await page.getByTestId("watched-row").getByRole("button", { name: "Stop watching" }).click();
  await expect(page.getByTestId("watched-row")).toHaveCount(0);
});
