import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 5.3. The test data has only a few closed deals, so a proposal is refused with the reason.
test("an admin asks for a learned proposal and is told when there is too little to learn from", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.getByRole("link", { name: "Learning", exact: true }).click();
  await page.getByRole("tab", { name: "Proposals" }).click();
  await expect(page.getByRole("heading", { name: "Learned proposals" })).toBeVisible();
  await page.getByRole("button", { name: "Propose scoring weights" }).click();
  await expect(page.getByText(/Not enough closed deals to learn from/)).toBeVisible();
  await expect(page.getByText("No proposals yet.")).toBeVisible();
});
