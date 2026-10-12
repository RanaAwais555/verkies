import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 4.4. Harbour Immigration Ltd exists from the earlier specs.
test("upload a document to an account, download it, and remove it", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.goto("/accounts");
  await page.getByLabel("Search accounts").fill("harbour");
  await page.getByTestId("accounts").getByRole("link", { name: "Harbour Immigration Ltd" }).click();
  await page.getByRole("tab", { name: "Documents" }).click();

  const panel = page.getByTestId("documents");
  await panel.getByRole("button", { name: "Upload", exact: true }).click();
  const form = page.getByTestId("upload-form");
  await form.getByLabel("File to upload").setInputFiles({ name: "Signed SOW.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7\n%%EOF\n") });
  await form.getByLabel("What it is").selectOption("sow");
  await form.getByRole("button", { name: "Upload", exact: true }).click();

  const doc = panel.getByTestId("document").filter({ hasText: "Signed SOW.pdf" });
  await expect(doc).toContainText("Statement of work");
  const download = page.waitForEvent("download");
  await doc.getByRole("link", { name: "Download" }).click();
  expect((await download).suggestedFilename()).toBe("Signed SOW.pdf");

  // A file that is not what its name says is refused.
  await panel.getByRole("button", { name: "Upload", exact: true }).click();
  await form.getByLabel("File to upload").setInputFiles({ name: "invoice.pdf", mimeType: "application/pdf", buffer: Buffer.from("<script>alert(1)</script>") });
  await form.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(form).toContainText("That file is not a PDF.");
  await form.getByRole("button", { name: "Cancel" }).click();

  await doc.getByRole("button", { name: "Remove Signed SOW.pdf" }).click();
  await doc.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(panel.getByTestId("document")).toHaveCount(0);
});
