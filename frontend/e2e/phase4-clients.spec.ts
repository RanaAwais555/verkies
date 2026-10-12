import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 4.1. Runs after the phase 3 specs: Harbour Immigration Ltd has a deal, lost on the board.
// Winning it back and converting it makes Harbour a client with a project.
test("win a deal, convert the account to a client, and work its project", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.getByRole("link", { name: "Pipeline", exact: true }).click();
  const harbour = page.getByTestId("deal").filter({ hasText: "Harbour Immigration Ltd" });
  await harbour.getByLabel("Move Harbour Immigration Ltd to").selectOption({ label: "Won" });
  await expect(page.getByTestId("stage-won")).toContainText("Harbour Immigration Ltd");

  await page.goto("/accounts");
  await page.getByLabel("Search accounts").fill("harbour");
  await page.getByTestId("accounts").getByRole("link", { name: "Harbour Immigration Ltd" }).click();
  await page.getByTestId("account-deals").getByRole("button", { name: "Convert to client" }).click();
  const form = page.getByTestId("convert-form");
  await form.getByRole("button", { name: "Add milestone" }).click();
  await form.getByLabel("Milestone 1", { exact: true }).fill("Designs signed off");
  await form.getByRole("button", { name: "Convert to client" }).click();

  // The project opens, with its milestone and a kick-off task.
  await page.waitForURL(/\/projects\/[0-9a-f-]+$/);
  await expect(page.getByTestId("milestones")).toContainText("Designs signed off");
  await expect(page.getByTestId("project-tasks")).toContainText("Kick off");
  await page.getByRole("checkbox", { name: "Mark reached: Designs signed off" }).click();
  await expect(page.getByTestId("milestones")).toContainText("1 of 1 reached");

  await page.getByRole("button", { name: "Raise a risk" }).click();
  await page.getByLabel("What could go wrong").fill("Content is not ready yet");
  await page.getByLabel("Severity").selectOption("high");
  await page.getByRole("button", { name: "Raise risk" }).click();
  await expect(page.getByText("1 high risk open")).toBeVisible();

  // The account is the same record, now a client.
  await page.getByRole("link", { name: "Harbour Immigration Ltd" }).click();
  await expect(page.getByText("Customer", { exact: true })).toBeVisible();
  await expect(page.getByText(/Account manager: .* client since/)).toBeVisible();

  await page.getByRole("link", { name: "Projects", exact: true }).click();
  await expect(page.getByTestId("project-row").filter({ hasText: "Harbour Immigration Ltd" })).toContainText("1 of 1 done");
});
