import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 3.5. Runs after the activities and email specs: Priya Shah (with an email address) is on
// Harbour Immigration Ltd, and sending is not configured, so nothing can go out.
test("enrol someone in a sequence, and work its first step from the queue", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.goto("/accounts");
  await page.getByLabel("Search accounts").fill("harbour");
  await page.getByTestId("accounts").getByRole("link", { name: "Harbour Immigration Ltd" }).click();

  // Every step is reviewed before approving.
  await page.getByRole("button", { name: "Enrol Priya Shah in a sequence" }).click();
  const panel = page.getByTestId("enroll-panel");
  await expect(panel).toContainText("Step 5");
  await expect(panel).toContainText("Hi Priya,");
  await panel.getByRole("button", { name: "Approve sequence" }).click();
  const priya = page.getByTestId("contact").filter({ hasText: "Priya Shah" });
  await expect(priya.getByTestId("enrollment")).toContainText("In Default outreach");

  // The first email waits in the queue; with sending not configured it cannot go out.
  await page.getByRole("link", { name: "Outreach", exact: true }).click();
  const item = page.getByTestId("queue-item").filter({ hasText: "Priya Shah" });
  await expect(item).toContainText("step 1 of 5");
  await expect(item.getByRole("button", { name: "Send" })).toBeDisabled();
  await expect(item).toContainText("Sending is switched off for VROS");
  await item.getByRole("button", { name: "Skip" }).click();
  await expect(page.getByTestId("queue-item").filter({ hasText: "Priya Shah" })).toHaveCount(0);

  await page.getByRole("tab", { name: "Sequences" }).click();
  await expect(page.getByTestId("sequences")).toContainText("Default outreach");
});
