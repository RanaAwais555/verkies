import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 3.1. Runs after the phase 1 and 2 specs: Harbour Immigration Ltd is an approved account
// with a website-rebuild opportunity and no deal yet.
test("open a deal from an opportunity, move it on the board, and lose it with a reason", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.goto("/accounts");
  await page.getByLabel("Search accounts").fill("harbour");
  await page.getByTestId("accounts").getByRole("link", { name: "Harbour Immigration Ltd" }).click();
  await page.getByRole("button", { name: "Open a deal" }).click();
  await expect(page.getByText("Deal: Qualified Opportunity")).toBeVisible();
  await expect(page.getByTestId("account-deals")).toContainText("Value unknown");

  await page.getByRole("link", { name: "Pipeline", exact: true }).click();
  const harbour = page.getByTestId("deal").filter({ hasText: "Harbour Immigration Ltd" });
  await expect(page.getByTestId("stage-qualified_opportunity")).toContainText("Harbour Immigration Ltd");
  await expect(harbour).toContainText("Value unknown");

  await harbour.getByLabel("Move Harbour Immigration Ltd to").selectOption({ label: "Proposal" });
  await expect(page.getByTestId("stage-proposal")).toContainText("Harbour Immigration Ltd");

  await harbour.getByLabel("Move Harbour Immigration Ltd to").selectOption({ label: "Lost" });
  const lost = page.getByTestId("lost-form");
  await lost.getByLabel("Lost reason").selectOption({ label: "Price" });
  await lost.getByRole("button", { name: "Mark as lost" }).click();
  await expect(page.getByTestId("stage-lost")).toContainText("Harbour Immigration Ltd");
  await expect(page.getByText(/Lost this year · 1/)).toBeVisible();
});
