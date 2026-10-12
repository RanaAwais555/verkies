import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 4.3. Runs after phase4-clients: Harbour Immigration Ltd is a client. Its expansion
// suggestions depend on what research found on the fixture site, so only the panel is checked;
// the referral it gives is followed through to the Referrals page.
test("see expansion on a client and log a referral it gave", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.goto("/accounts");
  await page.getByLabel("Search accounts").fill("harbour");
  await page.getByTestId("accounts").getByRole("link", { name: "Harbour Immigration Ltd" }).click();
  await page.getByRole("tab", { name: "Client" }).click();
  await expect(page.getByTestId("expansion")).toContainText(/Evidence, found|No expansion suggestions/);

  const referrals = page.getByTestId("account-referrals");
  await referrals.getByRole("button", { name: "Log a referral they gave" }).click();
  const form = page.getByTestId("referral-form");
  await form.getByLabel("Company they referred").fill("Northbridge Visas");
  await form.getByLabel("Its website (optional)").fill("northbridge-visas.test");
  await form.getByLabel("How they know Verkies (optional)").fill("Client");
  await form.getByRole("button", { name: "Log referral" }).click();
  await expect(referrals.getByTestId("referral-row")).toContainText("Northbridge Visas");

  await page.getByRole("link", { name: "Referrals", exact: true }).click();
  const row = page.getByTestId("referral-row").filter({ hasText: "Northbridge Visas" });
  await expect(row).toContainText("Harbour Immigration Ltd");
  await expect(row).toContainText("Not yet");
  await row.getByLabel("Status of the referral of Northbridge Visas").selectOption("contacted");
  await page.reload();
  await expect(page.getByLabel("Status of the referral of Northbridge Visas")).toHaveValue("contacted");
});
