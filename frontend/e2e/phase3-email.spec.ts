import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 3.4. Runs after the activities spec, which added Priya Shah (with an email address) to
// Harbour Immigration Ltd. The e2e stack never sets VROS_EMAIL_SENDING_ENABLED, so this checks
// that nothing can be sent without explicit configuration, and that the checks say why.
test("an email cannot be sent until sending is configured, and the checks say why", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.goto("/accounts");
  await page.getByLabel("Search accounts").fill("harbour");
  await page.getByTestId("accounts").getByRole("link", { name: "Harbour Immigration Ltd" }).click();
  await page.getByRole("button", { name: "Email Priya Shah" }).click();
  const composer = page.getByTestId("email-composer");
  const checks = composer.getByTestId("email-checks");
  await expect(checks).toContainText("Sending is switched off for VROS");
  await expect(checks).toContainText("Connect your mailbox in Settings");
  await expect(composer).toContainText('reply "no thanks"');
  await composer.getByLabel("Subject").fill("Client intake");
  await composer.getByLabel("Message").fill("Hi Priya, would a portal help?");
  await expect(composer.getByRole("button", { name: "Send" })).toBeDisabled();

  await page.goto("/settings?tab=mailbox");
  await expect(page.getByTestId("mailbox")).toContainText("Sending is switched off for VROS");
  await expect(page.getByTestId("mailbox-form").getByLabel("SMTP server")).toBeVisible();
  await expect(page.getByTestId("dns-checks")).toContainText("Connect a mailbox to see what to fix");
});
