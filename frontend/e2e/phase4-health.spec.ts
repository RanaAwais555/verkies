import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 4.2. Runs after phase4-clients: Harbour Immigration Ltd is a client whose project has a
// high risk open, so it is Red.
test("see a client at risk, run the retention check, and record feedback", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await expect(page.getByTestId("client-risks")).toContainText("Harbour Immigration Ltd");

  await page.getByRole("link", { name: "Clients", exact: true }).click();
  const harbour = page.getByTestId("client-row").filter({ hasText: "Harbour Immigration Ltd" });
  await expect(harbour).toContainText("Red");
  await expect(harbour).toContainText("high risk open: Content is not ready yet");

  await page.getByRole("button", { name: "Check now" }).click();
  await expect(page.getByText(/Checked \d+ clients?: \d+ changed colour, \d+ new risks? raised\./)).toBeVisible();

  await harbour.getByRole("link", { name: "Harbour Immigration Ltd" }).click();
  const panel = page.getByTestId("client-health");
  await expect(panel).toContainText("Red");
  await expect(page.getByTestId("health-history")).toContainText("Red");

  await panel.getByRole("button", { name: "Record feedback" }).click();
  await page.getByLabel("How they feel").selectOption("positive");
  await page.getByLabel("What they said (optional)").fill("Happy with the designs");
  await page.getByRole("button", { name: "Record feedback" }).click();
  await expect(page.getByTestId("feedback")).toContainText("Happy with the designs");

  // The retention engine gave the account manager a follow-up task.
  await page.getByRole("tab", { name: /Tasks/ }).click();
  await expect(page.getByText(/Client risk detected: talk to Harbour Immigration Ltd/)).toBeVisible();
});
