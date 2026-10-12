import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 6.3. The starting rules come from migration 0028; what a check flags depends on the
// fixture site's sources, so this covers the rules, editing them and the notifications page.
test("alert rules and notifications", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.goto("/monitoring");
  const rules = page.getByTestId("alert-rules");
  await expect(rules.getByTestId("rule-row").filter({ hasText: "Funding, acquisition or expansion" })).toContainText("Opportunity Detected");

  await rules.getByRole("button", { name: "New rule" }).click();
  const form = page.getByTestId("rule-form");
  await form.getByLabel("Rule name").fill("Technology changed (e2e)");
  await form.getByLabel("Then").selectOption("requires_review");
  await form.getByLabel("Website change", { exact: true }).check();
  await form.getByLabel("Technology", { exact: true }).check();
  await form.getByRole("button", { name: "Add rule" }).click();
  const added = rules.getByTestId("rule-row").filter({ hasText: "Technology changed (e2e)" });
  await expect(added).toContainText("about Technology");
  await added.getByRole("button", { name: "Delete Technology changed (e2e)" }).click();
  await added.getByRole("button", { name: "Confirm deleting Technology changed (e2e)" }).click();
  await expect(added).toHaveCount(0);

  await page.getByTestId("notification-bell").click();
  await expect(page.getByRole("heading", { name: "Notifications", level: 1 })).toBeVisible();
  await expect(page.getByLabel("Monitoring found something new on an account you watch")).toBeChecked();
});
