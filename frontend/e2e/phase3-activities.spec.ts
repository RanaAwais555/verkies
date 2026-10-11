import { expect, test } from "@playwright/test";

import { ADMIN } from "./env";

// Slice 3.2. Runs after the phase 1 and 2 specs (and before the deals spec, which still needs
// Harbour's opportunity without a deal): Harbour Immigration Ltd is an approved account.
test("add a person, log a call and their reply, and see the relationship and timeline", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();

  await page.goto("/accounts");
  await page.getByLabel("Search accounts").fill("harbour");
  await page.getByTestId("accounts").getByRole("link", { name: "Harbour Immigration Ltd" }).click();

  // Add someone the team knows.
  await page.getByRole("button", { name: "Add person" }).click();
  const person = page.getByTestId("contact-form");
  await person.getByLabel("Name").fill("Priya Shah");
  await person.getByLabel("Job title").fill("Operations Director");
  await person.getByLabel("Email").fill("priya@harbour.test");
  await person.getByLabel("Buying role").selectOption({ label: "Economic buyer" });
  await person.getByRole("button", { name: "Add person" }).click();
  const priya = page.getByTestId("contact").filter({ hasText: "Priya Shah" });
  await expect(priya).toContainText("Not contacted yet");
  await expect(priya).toContainText("added by the team");

  // An unanswered call, with a follow-up scheduled in the same step.
  await page.getByRole("button", { name: "Log activity" }).click();
  const log = page.getByTestId("log-activity");
  await log.getByRole("radio", { name: "Call" }).check();
  await log.getByLabel("With").selectOption({ label: "Priya Shah, Operations Director" });
  await log.getByLabel("How it went").selectOption({ label: "No answer" });
  await log.getByLabel("What was said or agreed").fill("Tried her direct line about the intake portal.");
  await log.getByLabel("Schedule a follow-up").check();
  await log.getByLabel("Follow-up", { exact: true }).fill("Call Priya again");
  await log.getByLabel("Due").fill("2030-02-01");
  await log.getByRole("button", { name: "Log call" }).click();
  const activities = page.getByTestId("activities");
  await expect(activities).toContainText("Call with Priya Shah, no answer");

  // Her reply by email.
  await log.getByRole("radio", { name: "Message" }).check();
  await log.getByLabel("With").selectOption({ label: "Priya Shah, Operations Director" });
  await log.getByLabel("Channel").selectOption({ label: "Email" });
  await log.getByLabel("Sent by").selectOption({ label: "Them (a reply or inbound message)" });
  await log.getByLabel("What was said or agreed").fill("Happy to talk on Thursday.");
  await log.getByRole("button", { name: "Log message" }).click();
  await expect(activities).toContainText("Email from Priya Shah");

  await page.getByRole("tab", { name: /^Tasks/ }).click();
  await expect(page.getByTestId("task").filter({ hasText: "Call Priya again" })).toBeVisible();

  await page.getByRole("tab", { name: "Overview" }).click();
  await expect(priya).toContainText("Replied");
  await expect(priya).toContainText("2 interactions");

  // Mark her details verified.
  await page.getByRole("button", { name: "Edit Priya Shah" }).click();
  await page.getByTestId("contact-form").getByLabel(/Verified/).check();
  await page.getByTestId("contact-form").getByRole("button", { name: "Save person" }).click();
  await expect(priya).toContainText("Verified");

  await page.getByRole("tab", { name: "Timeline" }).click();
  const timeline = page.getByTestId("timeline");
  await expect(timeline).toContainText("Contact added: Priya Shah, Operations Director.");
  await expect(timeline).toContainText("Call with Priya Shah, no answer: Tried her direct line about the intake portal.");
  await expect(timeline).toContainText("Email from Priya Shah: Happy to talk on Thursday.");
});
