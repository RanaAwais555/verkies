import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 3.3. Runs after the deals spec: Harbour Immigration Ltd's deal was lost for "Price".
test("dashboards explain their figures, and saved views open filtered pages", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.getByRole("link", { name: "Reports", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
  const lost = page.getByTestId("figure-win_rate");
  await expect(lost).toContainText("0%"); // one closed deal, lost
  await lost.getByRole("button", { name: "How it's counted" }).click();
  await expect(lost).toContainText("Deals won out of deals won or lost");
  await expect(page.getByTestId("funnel")).toContainText("Discovery");

  await page.getByRole("tab", { name: "Management" }).click();
  await expect(page.getByTestId("table-lost_reasons")).toContainText("Price");
  await page.getByRole("tab", { name: "Lead intelligence" }).click();
  await expect(page.getByTestId("figure-qualification_rate")).toBeVisible();

  // A team view opens its page with the filter applied.
  await page.goto("/views");
  const views = page.getByTestId("saved-views").first();
  await expect(views).toContainText("My Hot Leads");
  await views.getByRole("link", { name: "Unassigned Leads" }).click();
  await expect(page).toHaveURL(/\/leads\?q=unassigned\+leads/);
  await expect(page.getByTestId("interpretation")).toContainText("Accounts with no owner");

  // Save a search as a personal view.
  await page.goto("/leads?q=legal");
  await page.getByRole("button", { name: "Save view" }).click();
  await page.getByLabel("View name").fill("Legal leads");
  await page.getByTestId("save-view").getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved as “Legal leads”.")).toBeVisible();
  await page.goto("/views");
  await expect(page.getByTestId("saved-views").last()).toContainText("Legal leads");
});
