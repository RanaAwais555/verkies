import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 5.1. Harbour Immigration Ltd exists from the earlier specs.
test("give feedback on a lead", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.goto("/accounts");
  await page.getByLabel("Search accounts").fill("harbour");
  await page.getByTestId("accounts").getByRole("link", { name: "Harbour Immigration Ltd" }).click();

  const panel = page.getByTestId("sales-feedback");
  await panel.getByRole("button", { name: "Give feedback" }).click();
  const form = page.getByTestId("feedback-form");
  await form.getByLabel("Your feedback").selectOption({ label: "Good lead" });
  await form.getByLabel("Why (optional)").fill("Right size, clear need for a portal");
  await form.getByRole("button", { name: "Save feedback" }).click();
  await expect(page.getByTestId("feedback-list")).toContainText("Good lead");
  await expect(page.getByTestId("feedback-list")).toContainText("Right size, clear need for a portal");
});
